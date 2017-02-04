import time

from dingo.grid.mv_grid.models.models import Graph, Node
from dingo.grid.mv_grid.util import util, data_input
from dingo.grid.mv_grid.solvers import savings, local_search
from dingo.tools.geo import calc_geo_dist_vincenty, calc_geo_dist_matrix_vincenty, calc_geo_centre_point
from dingo.core.network.stations import *
from dingo.core.structure.regions import LVLoadAreaCentreDingo
from dingo.core.network import RingDingo, BranchDingo, CircuitBreakerDingo
from dingo.core.network.cable_distributors import MVCableDistributorDingo


def dingo_graph_to_routing_specs(graph):
    """ Build data dictionary from graph nodes for routing (translation)

    Args:
        graph: NetworkX graph object with nodes

    Returns:
        specs: Data dictionary for routing, See class `Graph()` in routing's model definition for keys
    """

    specs = {}
    nodes_demands = {}
    nodes_pos = {}
    nodes_agg = {}
    for node in graph.nodes():

        # station is LV station
        if isinstance(node, LVLoadAreaCentreDingo):
            # only major stations are connected via MV ring
            if not node.lv_load_area.is_satellite:
                # OLD: prior issue #51
                # nodes_demands[str(node)] = node.grid.grid_district.peak_load_sum
                nodes_demands[str(node)] = node.lv_load_area.peak_load_sum
                nodes_pos[str(node)] = (node.geo_data.x, node.geo_data.y)
                # get aggregation flag
                if node.lv_load_area.is_aggregated:
                    nodes_agg[str(node)] = True
                else:
                    nodes_agg[str(node)] = False

        # station is MV station
        elif isinstance(node, MVStationDingo):
            nodes_demands[str(node)] = 0
            nodes_pos[str(node)] = (node.geo_data.x, node.geo_data.y)
            specs['DEPOT'] = str(node)
            specs['BRANCH_KIND'] = node.grid.default_branch_kind
            specs['BRANCH_TYPE'] = node.grid.default_branch_type
            specs['V_LEVEL'] = node.grid.v_level
            specs['V_LEVEL_OP'] = node.v_level_operation

    specs['NODE_COORD_SECTION'] = nodes_pos
    specs['DEMAND'] = nodes_demands
    specs['MATRIX'] = calc_geo_dist_matrix_vincenty(nodes_pos)
    specs['IS_AGGREGATED'] = nodes_agg

    return specs


def routing_solution_to_dingo_graph(graph, solution):
    """ Insert `solution` from routing into `graph`

    Args:
        graph: NetworkX graph object with nodes
        solution: Instance of `BaseSolution` or child class (e.g. `LocalSearchSolution`) (=solution from routing)

    Returns:
        graph: NetworkX graph object with nodes and edges
    """
    # TODO: Bisherige Herangehensweise (diese Funktion): Branches werden nach Routing erstellt um die Funktionsfähigkeit
    # TODO: des Routing-Tools auch für die TestCases zu erhalten. Es wird ggf. notwendig, diese direkt im Routing vorzunehmen.

    # build node dict (name: obj) from graph nodes to map node names on node objects
    node_list = {str(n): n for n in graph.nodes()}

    # add edges from solution to graph
    try:
        depot = solution._nodes[solution._problem._depot.name()]
        depot_node = node_list[depot.name()]
        for r in solution.routes():
            circ_breaker_pos = None

            # if route has only one node and is not aggregated, it wouldn't be possible to add two lines from and to
            # this node (undirected graph of NetworkX). So, as workaround, an additional MV cable distributor is added
            # at nodes' position (resulting route: HV/MV_subst --- node --- cable_dist --- HV/MV_subst.
            if len(r._nodes) == 1:
                if not solution._problem._is_aggregated[r._nodes[0]._name]:
                    # create new cable dist
                    cable_dist = MVCableDistributorDingo(geo_data=node_list[r._nodes[0]._name].geo_data,
                                                         grid=depot_node.grid)
                    depot_node.grid.add_cable_distributor(cable_dist)

                    # create new node (as dummy) an allocate to route r
                    r.allocate([Node(name=repr(cable_dist), demand=0)])

                    # add it to node list and allocated-list manually
                    node_list[str(cable_dist)] = cable_dist
                    solution._problem._is_aggregated[str(cable_dist)] = False

                    # set circ breaker pos manually
                    circ_breaker_pos = 1

            # build edge list
            n1 = r._nodes[0:len(r._nodes)-1]
            n2 = r._nodes[1:len(r._nodes)]
            edges = list(zip(n1, n2))
            edges.append((depot, r._nodes[0]))
            edges.append((r._nodes[-1], depot))

            # create MV Branch object for every edge in `edges`
            mv_branches = [BranchDingo() for _ in edges]
            edges_with_branches = list(zip(edges, mv_branches))

            # recalculate circuit breaker positions for final solution, create it and set associated branch.
            # if circ. breaker position is not set manually (routes with more than one load area, see above)
            if not circ_breaker_pos:
                circ_breaker_pos = r.calc_circuit_breaker_position()

            node1 = node_list[edges[circ_breaker_pos - 1][0].name()]
            node2 = node_list[edges[circ_breaker_pos - 1][1].name()]

            # ALTERNATIVE TO METHOD ABOVE: DO NOT CREATE 2 BRANCHES (NO RING) -> LA IS CONNECTED AS SATELLITE
            # IF THIS IS COMMENTED-IN, THE IF-BLOCK IN LINE 87 HAS TO BE COMMENTED-OUT
            # ===============================
            # do not add circuit breaker for routes which are aggregated load areas or
            # routes that contain only one load area
            # if not (node1 == depot_node and solution._problem._is_aggregated[edges[circ_breaker_pos - 1][1].name()] or
            #         node2 == depot_node and solution._problem._is_aggregated[edges[circ_breaker_pos - 1][0].name()] or
            #         len(r._nodes) == 1):
            # ===============================

            # do not add circuit breaker for routes which are aggregated load areas
            if not (node1 == depot_node and solution._problem._is_aggregated[edges[circ_breaker_pos - 1][1].name()] or
                    node2 == depot_node and solution._problem._is_aggregated[edges[circ_breaker_pos - 1][0].name()]):
                branch = mv_branches[circ_breaker_pos - 1]
                circ_breaker = CircuitBreakerDingo(grid=depot_node.grid, branch=branch,
                                                   geo_data=calc_geo_centre_point(node1, node2))
                branch.circuit_breaker = circ_breaker

            # create new ring object for route
            ring = RingDingo(grid=depot_node.grid)

            # translate solution's node names to graph node objects using dict created before
            # note: branch object is assigned to edge using an attribute ('branch' is used here), it can be accessed
            # using the method `graph_edges()` of class `GridDingo`
            edges_graph = []
            for ((n1, n2), b) in edges_with_branches:
                # get node objects
                node1 = node_list[n1.name()]
                node2 = node_list[n2.name()]

                # set branch's ring attribute
                b.ring = ring

                # add load area to ring
                if isinstance(node1, LVLoadAreaCentreDingo):
                    ring.add_lv_load_area(node1.lv_load_area)

                # set branch length
                b.length = calc_geo_dist_vincenty(node1, node2)

                # set branch kind and type
                # 1) default
                b.kind = depot_node.grid.default_branch_kind
                b.type = depot_node.grid.default_branch_type
                # 2) aggregated load area types
                if node1 == depot_node and solution._problem._is_aggregated[n2.name()]:
                    b.connects_aggregated = True
                    b.kind = depot_node.grid.default_branch_kind_aggregated
                    b.type = depot_node.grid.default_branch_type_aggregated
                elif node2 == depot_node and solution._problem._is_aggregated[n1.name()]:
                    b.connects_aggregated = True
                    b.kind = depot_node.grid.default_branch_kind_aggregated
                    b.type = depot_node.grid.default_branch_type_aggregated

                # append to branch list
                edges_graph.append((node1, node2, dict(branch=b)))

            # add branches to graph
            graph.add_edges_from(edges_graph)

    except:
        print('unexpected error while converting routing solution to DINGO graph (NetworkX).')

    return graph


def solve(graph, debug=False, anim=None):
    """ Do MV routing for given nodes in `graph`. Translate data from node objects to appropriate format before.

    Args:
        graph: NetworkX graph object with nodes
        debug: If True, information is printed while routing
        anim: AnimationDingo object (refer to class 'AnimationDingo()' for a more detailed description)

    Returns:
        graph: NetworkX graph object with nodes and edges
    """

    # TODO: Implement debug mode (pass to solver) to get more information while routing (print routes, draw network, ..)

    # translate DINGO graph to routing specs
    specs = dingo_graph_to_routing_specs(graph)

    # create routing graph using specs
    RoutingGraph = Graph(specs)

    timeout = 30000

    # create solver objects
    savings_solver = savings.ClarkeWrightSolver()
    local_search_solver = local_search.LocalSearchSolver()

    start = time.time()

    # create initial solution using Clarke and Wright Savings methods
    savings_solution = savings_solver.solve(RoutingGraph, timeout, debug, anim)

    # OLD, MAY BE USED LATER - Guido, please don't declare a variable later=now() :) :
    #if not savings_solution.is_complete():
    #    print('=== Solution is not a complete solution! ===')

    if debug:
        print('ClarkeWrightSolver solution:')
        util.print_solution(savings_solution)
        print('Elapsed time (seconds): {}'.format(time.time() - start))
        #savings_solution.draw_network()

    # improve initial solution using local search
    local_search_solution = local_search_solver.solve(RoutingGraph, savings_solution, timeout, debug, anim)
    #local_search_solution = savings_solution

    if debug:
        print('Local Search solution:')
        util.print_solution(local_search_solution)
        print('Elapsed time (seconds): {}'.format(time.time() - start))
        #local_search_solution.draw_network()

    return routing_solution_to_dingo_graph(graph, local_search_solution)
