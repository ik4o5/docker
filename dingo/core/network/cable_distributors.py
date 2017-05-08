from . import CableDistributorDingo


class MVCableDistributorDingo(CableDistributorDingo):
    """ MV Cable distributor (connection point) """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.lv_load_area_group = kwargs.get('lv_load_area_group', None)
        self.id_db = self.grid.cable_distributors_count() + 1

    @property
    def pypsa_id(self):

        return '_'.join(['MV', str(self.grid.id_db),
                                  'cld', str(self.id_db)])

    def __repr__(self):
        return 'mv_cable_dist_' + str(self.id_db)


class LVCableDistributorDingo(CableDistributorDingo):
    """ LV Cable distributor (connection point) """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.string_id = kwargs.get('string_id', None)
        self.branch_no = kwargs.get('branch_no', None)
        self.load_no = kwargs.get('load_no', None)
        self.id_db = self.grid.cable_distributors_count() + 1
        self.in_building = kwargs.get('in_building', False)

    def __repr__(self):
        return 'lv_cable_dist_' + str(self.id_db)
