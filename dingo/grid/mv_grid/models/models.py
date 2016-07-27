"""
    Copyright 2016 openego development group
    Licensed under GNU General Public License 3.0. See the LICENSE file at the
    top-level directory of this distribution or obtain a copy of the license at
    http://www.gnu.org/licenses/gpl-3.0.txt
    
    Based on code by Romulo Oliveira copyright (C) 2015,
    https://github.com/RomuloOliveira/monte-carlo-cvrp
    Originally licensed under the Apache License, Version 2.0. You may obtain a
    copy of the license at http://www.apache.org/licenses/LICENSE-2.0
"""

from dingo.tools import config as cfg_dingo

from math import pi, tan, acos


class CableType(object):
    def __init__(self, cabletype_id):
        #for cable_no in range(1,2)
        cables = {1: {'name': 'Al185', 'r': 0.164, 'x': 0.090, 'c': 550, 'g': 520, 'i_max_th': 295},
                  2: {'name': 'Al240', 'r': 0.125, 'x': 0.089, 'c': 610, 'g': 640, 'i_max_th': 343}}
        
        self.cabletype_id = cabletype_id
        self.name = cables[cabletype_id]['name']
        self.r = cables[cabletype_id]['r']
        self.x = cables[cabletype_id]['x']
        self.c = cables[cabletype_id]['c']
        self.g = cables[cabletype_id]['g']
        self.i_max_th = cables[cabletype_id]['i_max_th']

#class Ring(object):
#    """
#    params for CVRP route
#    """
#    
#    def __init__(self, route):
#        self._routes = []


class Route(object):
    """
    CVRP route, consists of consecutive nodes
    -----------------------------------------
    bla
    """

    def __init__(self, cvrp_problem, capacity):
        """Class constructor

        Initialize route capacity

        Parameters:
            capacity: route capacity
        """
        self._problem = cvrp_problem
        self._capacity = capacity
        self._demand = 0
        self._nodes = []

    def capacity(self):
        """Returns the route capacity"""
        return self._capacity

    def demand(self):
        """Returns the current route demand"""
        return self._demand

    def nodes(self):
        """Returns a generator for iterating over nodes"""
        for node in self._nodes:
            yield node

    def length(self):
        """Returns the route length (cost)"""
        cost = 0
        depot = self._problem.depot()

        last = depot
        for i in self._nodes:
            a, b = last, i
            if a.name() > b.name():
                a, b = b, a

            cost = cost + self._problem.distance(a, b)
            last = i

        cost = cost + self._problem.distance(depot, last)

        return cost

    def can_allocate(self, nodes):
        """Returns True if this route can allocate nodes in `nodes` list"""
        nodes_demand = sum([node.demand() for node in nodes])

        if self.tech_constraints_satisfied():
            return True

        #if self._demand + nodes_demand <= self._capacity:
        #    return True

        return False
        
    def can_exchange_nodes(self, target_route, nodes, target_nodes):
        """Returns True if this route can insert `nodes` (list) into route
        `target_route` and insert `target_nodes` into self regarding `routes`'
        and `target_routes`' capacities."""
        
        nodes_demand = sum([node.demand() for node in nodes])
        target_nodes_demand = sum([node.demand() for node in target_nodes])

        if (self._demand - nodes_demand + target_nodes_demand <= self._capacity and
            target_route._demand - target_nodes_demand + nodes_demand <= target_route._capacity):
            return True

        return False

    def allocate(self, nodes, append=True):
        """Allocates all nodes from `nodes` list in this route"""

        # TEMPORÄR RAUS. SPÄTER WIEDER REIN!!
        #if not self.can_allocate(nodes):
        #    raise Exception('Trying to allocate more than route capacity')

        nodes_demand = 0
        for node in [node for node in nodes]:
            if node._allocation:
                node._allocation.deallocate([node])

            node._allocation = self
            nodes_demand = nodes_demand + node.demand()
            if append:
                self._nodes.append(node)
            else:
                self._nodes.insert(0, node)

        self._demand = self._demand + nodes_demand

    def deallocate(self, nodes):
        """Deallocates all nodes from `nodes` list from this route"""

        nodes_demand = 0
        for node in nodes:
            self._nodes.remove(node)
            node._allocation = None
            nodes_demand = nodes_demand + node.demand()

        self._demand = self._demand - nodes_demand

        if self._demand < 0:
            raise Exception('Trying to deallocate more than previously allocated')
    
    def insert(self, nodes, pos):
        """Inserts all nodes from `nodes` list into this route at position `pos`"""
        
        # TODO: TEMPORÄR RAUS. SPÄTER WIEDER REIN!!
        #if not self.can_allocate(nodes):
        #    raise Exception('Trying to allocate more than route capacity')
        
        node_list = []
        nodes_demand = 0
        for node in [node for node in nodes]:
            if node._allocation:
                node._allocation.deallocate([node])
            node_list.append(node)
            node._allocation = self
            nodes_demand = nodes_demand + node.demand()

        self._nodes = self._nodes[:pos] + node_list + self._nodes[pos:]
        self._demand += nodes_demand

    def is_interior(self, node):
        """Returns True if node is interior to the route, i.e., not adjascent to depot"""
        return self._nodes.index(node) != 0 and self._nodes.index(node) != len(self._nodes) - 1

    def last(self, node):
        """Returns True if node is the last node in the route"""
        return self._nodes.index(node) == len(self._nodes) - 1

    def calc_circuit_breaker_position(self, debug=False):
        """ Calculates the optimal position of a circuit breaker on route.

        Returns:
            OLD: 2-tuple of nodes (instances of Node class) = route segment
            position of circuit breaker on route (index of last node on 1st half-ring preceding the circuit breaker)

        Notes
        -----
        According to planning principles of MV grids, a MV ring is run as two strings (half-rings) separated by a
        circuit breaker which is open at normal operation.
        Assuming a ring (route which is connected to the root node at either sides), the optimal position of a circuit
        breaker is defined as the position (virtual cable) between two nodes where the conveyed current is minimal on
        the route.

        References
        ----------

        """
        # TODO: add references (Tao)

        # set init value
        demand_diff_min = 10e6

        # check possible positions in route
        for ctr in range(len(self._nodes)):
            # split route and calc demand difference
            route_demand_part1 = sum([node.demand() for node in self._nodes[0:ctr]])
            route_demand_part2 = sum([node.demand() for node in self._nodes[ctr:len(self._nodes)]])
            demand_diff = abs(route_demand_part1 - route_demand_part2)

            if demand_diff < demand_diff_min:
                demand_diff_min = demand_diff
                position = ctr

        if debug:
            print('sum 1=', sum([node.demand() for node in self._nodes[0:position]]))
            print('sum 2=', sum([node.demand() for node in self._nodes[position:len(self._nodes)]]))
            print('Position of circuit breaker: ', self._nodes[position-1], '-', self._nodes[position], '(sumdiff=', demand_diff_min, ')')

        #return self._nodes[position-1], self._nodes[position]
        return position
        
    def tech_constraints_satisfied(self):
        """ Check route validity according to technical constraints
        
        Constraints:
            current rating of cable/line
            voltage stability at all nodes
            cable/line losses?
        """
        ### CHECK WITH ROUTE CAPACITY (see also: solution.is_complete AND route.can_allocate)
        # TODO: TO BE COMPLETED

        # load parameters
        load_factor_line_normal = float(cfg_dingo.get('assumptions',
                                                      'load_factor_line_normal'))
        load_factor_cable_normal = float(cfg_dingo.get('assumptions',
                                                       'load_factor_cable_normal'))
        load_factor_line_malfunc = float(cfg_dingo.get('assumptions',
                                                       'load_factor_line_malfunc'))
        load_factor_cable_malfunc = float(cfg_dingo.get('assumptions',
                                                        'load_factor_cable_malfunc'))
        mv_max_v_level_diff_normal = float(cfg_dingo.get('mv_routing_tech_constraints',
                                                         'mv_max_v_level_diff_normal'))
        mv_max_v_level_diff_malfunc = float(cfg_dingo.get('mv_routing_tech_constraints',
                                                          'mv_max_v_level_diff_malfunc'))

        # step 1: calc circuit breaker position
        position = self.calc_circuit_breaker_position()

        # step 2: calc required values for checking current & voltage
        # get nodes of half-rings
        nodes_hring1 = [self._problem._depot] + self._nodes[0:position]
        nodes_hring2 = list(reversed(self._nodes[position:len(self._nodes)] + [self._problem._depot]))

        # factor to calc reactive from active power
        # TODO: move cos_phi to config
        Q_factor = tan(acos(0.95))

        # line/cable params per km
        r = self._problem._branch_type['R']  # unit: ohm/km
        x = self._problem._branch_type['L'] * 2*pi * 50 / 1e3  # unit: ohm/km

        # step 3a: check if current rating of default cable/line is violated
        # (for every of the 2 half-rings using load factor for normal operation)
        demand_hring_1 = sum([node.demand() for node in self._nodes[0:position]])
        demand_hring_2 = sum([node.demand() for node in self._nodes[position:len(self._nodes)]])
        peak_current_sum_hring1 = demand_hring_1 * (3**0.5) / self._problem._v_level  # units: kVA / kV = A
        peak_current_sum_hring2 = demand_hring_2 * (3**0.5) / self._problem._v_level  # units: kVA / kV = A

        if (peak_current_sum_hring1 > (self._problem._branch_type['I_max_th'] * load_factor_line_normal) or
            peak_current_sum_hring2 > (self._problem._branch_type['I_max_th'] * load_factor_line_normal)):
            return False

        # step 3b: check if current rating of default cable/line is violated
        # (for full ring using load factor for malfunction operation)
        peak_current_sum_ring = self._demand * (3**0.5) / self._problem._v_level  # units: kVA / kV = A
        if peak_current_sum_ring > (self._problem._branch_type['I_max_th'] * load_factor_line_malfunc):
            return False

        # step 4a: check voltage stability at all nodes
        # (for every of the 2 half-rings using max. voltage difference for normal operation)
        # TODO: MOVE DETOUR FACTOR TO PLACE PRIOR TO ROUTING TO GET REAL DISTANCES HERE! (see mv_routing)

        # get operation voltage level from station
        v_level_hring1 = v_level_hring2 = v_level_ring_dir1 = v_level_ring_dir2 = v_level_op = self._problem._v_level_operation * 1e3

        for n1, n2 in zip(nodes_hring1[0:len(nodes_hring1)-1], nodes_hring1[1:len(nodes_hring1)]):
            v_level_hring1 -= n2.demand() * 1e3 * self._problem.distance(n1, n2) * (r + x*Q_factor) / v_level_hring1
            if (v_level_op - v_level_hring1) > (v_level_op * mv_max_v_level_diff_normal):
                return False

        for n1, n2 in zip(nodes_hring2[0:len(nodes_hring2)-1], nodes_hring2[1:len(nodes_hring2)]):
            v_level_hring2 -= n2.demand() * 1e3 * self._problem.distance(n1, n2) * (r + x*Q_factor) / v_level_hring2
            if (v_level_op - v_level_hring2) > (v_level_op * mv_max_v_level_diff_normal):
                return False

        # step 4b: check voltage stability at all nodes
        # (for full ring using max. voltage difference for malfunction operation)
        for (n1, n2), (n3, n4) in zip(zip(nodes_hring1[0:len(nodes_hring1)-1], nodes_hring1[1:len(nodes_hring1)]),
                                      zip(nodes_hring2[0:len(nodes_hring2)-1], nodes_hring2[1:len(nodes_hring2)])):
            v_level_ring_dir1 -= n2.demand() * 1e3 * self._problem.distance(n1, n2) * (r + x*Q_factor) / v_level_ring_dir1
            v_level_ring_dir2 -= n4.demand() * 1e3 * self._problem.distance(n3, n4) * (r + x*Q_factor) / v_level_ring_dir2
            if ((v_level_op - v_level_ring_dir1) > (v_level_op * mv_max_v_level_diff_malfunc) or
                (v_level_op - v_level_ring_dir1) > (v_level_op * mv_max_v_level_diff_malfunc)):
                return False

        #for node1, node2 in zip(self._nodes[0:len(self._nodes)-1], self._nodes[1:len(self._nodes)]):
        #    v_level_ring -= node2.demand() * self._problem.distance(node1, node2) * (r + x*Q_factor) / v_level_ring
        #    if (v_level_op - v_level_ring) > (v_level_op * mv_max_v_level_diff_malfunc):
        #       return False

        return True


    def __str__(self):
        return str(self._nodes)

    def __repr__(self):
        return str(self._nodes)


class Node(object):
    """
    CVRP node (MV transformer/customer)
    -----------------------------------
    bla
    """

    def __init__(self, name, demand):
        """Class constructor

        Initialize demand

        Parameters:
            name: Node name
            demand: Node demand
        """
        self._name = name
        self._demand = demand
        self._allocation = None

    def name(self):
        """Returns node name"""
        return self._name

    def demand(self):
        """Returns the node demand"""
        return self._demand

    def route_allocation(self):
        """Returns the route which node is allocated"""
        return self._allocation

    def __str__(self):
        return str(self._name)

    def __repr__(self):
        return str(self._name)

    def __cmp__(self, other):
        if isinstance(other, Node):
            return self._name - other._name

        return self._name - other

    def __hash__(self):
        return self._name.__hash__()


class Graph(object):
    """Class for modelling a CVRP problem data"""
    """
    CVRP graph
    ----------
    bla
    """

    def __init__(self, data):
        """Class constructor

        Initialize all nodes, edges and depot

        Parameters:
            data: TSPLIB parsed data
        """
        
        self._coord = data['NODE_COORD_SECTION']
        self._nodes = {i: Node(i, data['DEMAND'][i]) for i in data['MATRIX']}
        self._matrix = {}
        self._capacity = data['CAPACITY']
        self._depot = None
        self._branch_type = data['BRANCH_TYPE']
        self._v_level = data['V_LEVEL']
        self._v_level_operation = data['V_LEVEL_OP']
        #self._voltage = data['VOLTAGE']
        #self._cabletype = CableType(data['CABLETYPE'])

        for i in data['MATRIX']:

            x = self._nodes[i]
            self._matrix[x] = {}

            if i == data['DEPOT']:
                self._depot = x # x, not i!!

            for j in data['MATRIX']:
                #if i == j:
                #    continue

                y = self._nodes[j]

                self._matrix[x][y] = data['MATRIX'][i][j]

        if self._depot is None:
            raise Exception('Depot not found')

    def nodes(self):
        """Returns a generator for iterating over nodes"""
        for i in sorted(self._nodes):
            yield self._nodes[i]

    def edges(self):
        """Returns a generator for iterating over edges"""
        for i in sorted(self._matrix.keys(), key=lambda x:x.name()):
            for j in sorted(self._matrix[i].keys(), key=lambda x:x.name()):
                if i != j:
                    yield (i, j)

    def depot(self):
        """Returns the depot node"""
        return self._depot

    def distance(self, i, j):
        """Returns the distance between node i and node j"""
        #a = i
        #b = j
        a, b = i, j

        if a.name() > b.name():
            #c = a            
            #a = b
            #b = c
            a, b = b, a
            
        #print(a, b)
        #if b.name() == '7'
        #return self._matrix[a][b]
        
        return self._matrix[self._nodes[a.name()]][self._nodes[b.name()]]

    def capacity(self):
        """Returns vehicles capacity"""
        return self._capacity