from scipy.sparse import coo_matrix

class Network:
    def __init__(self, buses, trafo2W, trafo3W, lines, generators, loads, xtGrids):
        self.buses = buses
        self.trafo2W = trafo2W
        self.trafo3W = trafo3W
        self.lines = lines
        self.generators = generators
        self.loads = loads
        self.xtGrids = xtGrids

        self.num_buses = len(self.buses)

        # compute invariate parameters
        self.build_passive_ybus()
        self.active_impedance_cache()

    def build_passive_ybus(self):
        '''
            build Y bus matrix from the edges (loop each element only once)
        '''
        rows = []
        cols = []
        Ydata = []

        '''
            build passive Y bus
        '''
        # add each line element
        for element in self.lines.values():
            
            # if status is False (element is off)
            if not element.status:
                continue

            r, c, d = element.get_Y()

            rows.extend(r)
            cols.extend(c)
            Ydata.extend(d)

        # add each two-winding trafo element
        for element in self.trafo2W.values():
            
            # if status is False (element is off)
            if not element.status:
                continue
            
            r, c, d = element.get_Y()

            rows.extend(r)
            cols.extend(c)
            Ydata.extend(d)

        # add each three-winding trafo element
        for element in self.trafo3W.values():
            
            # if status is False (element is off)
            if not element.status:
                continue
            
            r, c, d = element.get_Y()

            rows.extend(r)
            cols.extend(c)
            Ydata.extend(d)
        
        self.passive_YBus = coo_matrix((Ydata, (rows, cols)), shape=(self.num_buses, self.num_buses)).tocsc()

    def active_impedance_cache(self):
        '''
            build `cache` for generators, loads and external grids: {'Element_Name': (row, column, data), ...}
            this will be used with the element states to compose the final Y matrix

            i) the generators have key as `Element_Name` not `Element_ID` because of the relation
            with `generatorcircuitbreaker_dimtable`

            ii) loads will be always on for now, so no issue with key

            iii) external grids does not have a uuid, using node name, same as self.xtGrids

        '''

        self.gen_cache = {}
        self.load_cache = {}
        self.grid_cache = {}

        # for each generator element
        for _, element in self.generators.items():
            self.gen_cache[element.name] = element.get_Y()

        # for each load element
        for k, element in self.loads.items():
            self.load_cache[k] = element.get_Y()

        # for each external grid element
        for k, element in self.xtGrids.items():
            self.grid_cache[k] = element.get_Y()

    def reload(self):
        '''
            to update the variables in case the equipments data changes
            the trigger of this function is not yet implemented
        '''
        self.build_passive_ybus()
        self.active_impedance_cache()

    def build_Y_system(self, gen_status, grid_status={}, load_status={}):
        '''
            status: the state of generators
                {'Element_Name': bool, ...}
        '''

        rows = []
        cols = []
        Ydata = []

        for name, (r, c, d) in self.gen_cache.items():
            
            # note that if not found or KeyError it consider the element `ON`
            if gen_status.get(name, True):
                rows.extend(r)
                cols.extend(c)
                Ydata.extend(d)

        for name, (r, c, d) in self.grid_cache.items():
            
            # note that if not found or KeyError it consider the element `ON`
            if grid_status.get(name, True):
                rows.extend(r)
                cols.extend(c)
                Ydata.extend(d)

        for name, (r, c, d) in self.load_cache.items():
            
            # note that if not found or KeyError it consider the element `ON`
            if load_status.get(name, True):
                rows.extend(r)
                cols.extend(c)
                Ydata.extend(d)
        
        Y_gen = coo_matrix((Ydata, (rows, cols)), shape=(self.num_buses, self.num_buses)).tocsc()

        return self.passive_YBus + Y_gen