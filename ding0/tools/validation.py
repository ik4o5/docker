"""This file is part of DINGO, the DIstribution Network GeneratOr.
DINGO is a tool to generate synthetic medium and low voltage power
distribution grids based on open data.

It is developed in the project open_eGo: https://openegoproject.wordpress.com

DING0 lives at github: https://github.com/openego/ding0/
The documentation is available on RTD: http://ding0.readthedocs.io"""

__copyright__  = "Reiner Lemoine Institut gGmbH"
__license__    = "GNU Affero General Public License Version 3 (AGPL-3.0)"
__url__        = "https://github.com/openego/ding0/blob/master/LICENSE"
__author__     = "nesnoj, gplssm"


import pickle
import os
import pandas as pd
import time
import numpy as np

import oemof.db as db
from ding0.tools.results import load_nd_from_pickle
from ding0.core import GeneratorDing0, LVLoadDing0

########################################################
def validate_generation(conn, file = 'ding0_tests_grids_1.pkl'):
    '''Validate if total generation of a grid in a pkl file is what expected.
    
    Parameters
    ----------
    conn:
        The connection
    file: str
        name of file containing a grid to compare.
        
    Returns
    -------
    DataFrame
        compare_by_level
    DataFrame
        compare_by_type
    '''
    #load network
    nw = load_nd_from_pickle(filename=file)

    #config network intern variables
    nw._config = nw.import_config()
    nw._pf_config = nw.import_pf_config()
    nw._static_data = nw.import_static_data()
    nw._orm = nw.import_orm()

    #rescue generation from input table
    generation_input = nw.list_generators(conn)

    #make table of generators that are in the grid
    gen_idx = 0
    gen_dict = {}
    for mv_district in nw.mv_grid_districts():
        #search over MV grid
        for node in mv_district.mv_grid.graph_nodes_sorted():
            if isinstance(node, GeneratorDing0):
                gen_idx+=1
                subtype = node.subtype
                if subtype == None:
                    subtype = 'other'
                type = node.type
                if type == None:
                    type = 'other'
                gen_dict[gen_idx] = {
                    'v_level':node.v_level,
                    'type':type,
                    'subtype':subtype,
                    'GenCap':node.capacity,
                }

        #search over LV grids
        for LA in mv_district.lv_load_areas():
            for lv_district in LA.lv_grid_districts():
                # generation capacity
                for g in lv_district.lv_grid.generators():
                    gen_idx+=1
                    subtype = g.subtype
                    if subtype == None:
                        subtype = 'other'
                    type = g.type
                    if type == None:
                        type = 'other'
                    gen_dict[gen_idx] = {
                        'v_level':g.v_level,
                        'type':type,
                        'subtype':subtype,
                        'GenCap':g.capacity,
                    }

    generation_effective = pd.DataFrame.from_dict(gen_dict, orient='index')

    #compare by voltage level
    input_by_level = generation_input.groupby('v_level').sum()['GenCap'].apply(lambda x: np.round(x,3))
    effective_by_level = generation_effective.groupby('v_level').sum()['GenCap'].apply(lambda x: np.round(x,3))

    compare_by_level = pd.concat([input_by_level,effective_by_level,input_by_level==effective_by_level],axis=1)
    compare_by_level.columns = ['before','after','equal?']

    #compare by type/subtype
    generation_input['type'] =generation_input['type']+'/'+generation_input['subtype']
    generation_effective['type'] =generation_effective['type']+'/'+generation_effective['subtype']

    input_by_type = generation_input.groupby('type').sum()['GenCap'].apply(lambda x: np.round(x,3))
    effective_by_type = generation_effective.groupby('type').sum()['GenCap'].apply(lambda x: np.round(x,3))

    compare_by_type = pd.concat([input_by_type,effective_by_type,input_by_type==effective_by_type],axis=1)
    compare_by_type.columns = ['before','after','equal?']
    compare_by_type.index.names = ['type/subtype']

    return compare_by_level, compare_by_type

########################################################
def validate_load_areas(conn, file = 'ding0_tests_grids_1.pkl'):
    '''Validate if total load of a grid in a pkl file is what expected.
    
    Parameters
    ----------
    conn:
        The connection
    file: str
        name of file containing a grid to compare.
        
    Returns
    -------
    DataFrame
        compare_by_sector
    '''
    #load network
    nw = load_nd_from_pickle(filename=file)

    #config network intern variables
    nw._config = nw.import_config()
    nw._pf_config = nw.import_pf_config()
    nw._static_data = nw.import_static_data()
    nw._orm = nw.import_orm()

    #rescue peak load from input table
    load_input = nw.list_load_areas(conn,nw.mv_grid_districts())
    la_input = sorted(load_input.index)
    load_input = load_input.sum(axis=0).apply(lambda x: np.round(x,3))
    load_input.sort_index(inplace=True)

    #search for LA in the grid
    lv_dist_idx = 0
    lv_dist_dict = {}
    la_idx = 0
    la_dict = {}
    lv_load_idx = 0
    lv_load_dict = {}
    for mv_district in nw.mv_grid_districts():
        for LA in mv_district.lv_load_areas():
            la_idx +=1
            la_dict[la_idx] = {
                'id_db':LA.id_db,
                'peak_load_residential':LA.peak_load_residential,
                'peak_load_retail':LA.peak_load_retail,
                'peak_load_industrial':LA.peak_load_industrial,
                'peak_load_agricultural':LA.peak_load_agricultural,
            }
            for lv_district in LA.lv_grid_districts():
                lv_dist_idx += 1
                lv_dist_dict[lv_dist_idx] = {
                    'id_db':lv_district.id_db,
                    'peak_load_residential':lv_district.peak_load_residential,
                    'peak_load_retail':lv_district.peak_load_retail,
                    'peak_load_industrial':lv_district.peak_load_industrial,
                    'peak_load_agricultural':lv_district.peak_load_agricultural,
                }
                for node in lv_district.lv_grid.graph_nodes_sorted():
                    if isinstance(node,LVLoadDing0):
                        lv_load_idx +=1
                        peak_load_agricultural = 0
                        peak_load_residential = 0
                        peak_load_retail = 0
                        peak_load_industrial = 0
                        if isinstance(node.consumption, dict):
                            #print(node.consumption)
                            if 'agricultural' in node.consumption:
                                tipo = 'agricultural'
                                peak_load_agricultural = node.peak_load
                            else:
                                tipo = 'ind_ret'
                                peak_load_industrial = node.peak_load
                        else:
                            tipo = 'residential'
                            peak_load_residential = node.peak_load
                        lv_load_dict[lv_load_idx] = {
                            'id_db':lv_district.id_db,
                            'peak_load_residential':peak_load_residential,
                            'peak_load_retail':peak_load_retail,
                            'peak_load_industrial':peak_load_industrial,
                            'peak_load_agricultural':peak_load_agricultural,
                        }

    #compare by LV district
    load_effective_lv_distr = pd.DataFrame.from_dict(lv_dist_dict,orient='index').set_index('id_db').sum(axis=0).apply(lambda x: np.round(x,3))
    load_effective_lv_distr.sort_index(inplace=True)

    compare_by_district = pd.concat([load_input,load_effective_lv_distr,load_input==load_effective_lv_distr],axis=1)
    compare_by_district.columns = ['before','after','equal?']
    compare_by_district.index.names = ['sector']

    #compare by LV Loads
    load_effective_lv_load = pd.DataFrame.from_dict(lv_load_dict,orient='index').set_index('id_db')
    #print(load_effective_lv_load)
    load_effective_lv_load = load_effective_lv_load.sum(axis=0).apply(lambda x: np.round(x,3))
    load_effective_lv_load.sort_index(inplace=True)

    compare_by_load = pd.concat([load_input,load_effective_lv_load,load_input==load_effective_lv_load],axis=1)
    compare_by_load.columns = ['before','after','equal?']
    compare_by_load.index.names = ['sector']

    #compare by LA
    load_effective = pd.DataFrame.from_dict(la_dict,orient='index').set_index('id_db')
    la_effective = sorted(load_effective.index)
    load_effective = load_effective.sum(axis=0).apply(lambda x: np.round(x,3))
    load_effective.sort_index(inplace=True)

    compare_by_la = pd.concat([load_input,load_effective,load_input==load_effective],axis=1)
    compare_by_la.columns = ['before','after','equal?']
    compare_by_la.index.names = ['sector']

    return compare_by_la, compare_by_district, compare_by_load, la_input==la_effective

########################################################
if __name__ == "__main__":
    conn = db.connection(section='oedb')

    #compare_by_level, compare_by_type = validate_generation(conn)
    #print(compare_by_level)
    #print(compare_by_type)

    compare_by_la, compare_by_district, compare_by_load, compare_la_ids = validate_load_areas(conn)
    print(compare_by_la)
    print(compare_by_district)
    print(compare_by_load)
    print(compare_la_ids)

    conn.close()