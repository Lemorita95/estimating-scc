import numpy as np
from cmath import polar, rect, pi
from math import pow, sqrt


class Bus:
    def __init__(self, element_id, name, Vb):
        self.element_id = element_id
        self.name = name
        self.Vb = float(Vb)


class Line:
    def __init__(self, element_id, name, bus_1, bus_2, length, r_km, x_km, c_km, status=True):
        self.element_id = element_id
        self.name = name
        self.bus_1 = bus_1
        self.bus_2 = bus_2
        self.length = float(length)
        self.Z_series = (float(r_km) + 1j* float(x_km)) * self.length
        self.Y_shunt = 1j* (2 * pi * 50) * (float(c_km) * 1e-9) * self.length
        self.status = status


    def to_pu(self, Vb, Sb=100):
        '''
            convert impedances to per-unit system
        '''
        Zb = pow(Vb, 2) / Sb
        self.Z_series = self.Z_series / Zb
        self.Y_shunt = self.Y_shunt / (1/Zb)

    def get_Y(self):
        rows = [self.bus_1.uuid, self.bus_1.uuid, self.bus_2.uuid, self.bus_2.uuid]
        cols = [self.bus_1.uuid, self.bus_2.uuid, self.bus_1.uuid, self.bus_2.uuid]
        Ydata = [1/self.Z_series + self.Y_shunt/2 if i == j else -1/self.Z_series for i, j in zip(rows,cols)]
        return (rows, cols, Ydata)


class Transformer:
    def __init__(self, element_id, bus_1, bus_2, name, Vn1, Vn2, Sn, Vsc, Vr, status=True):
        self.element_id = element_id
        self.name = name
        self.bus_1 = bus_1
        self.bus_2 = bus_2
        self.Vn1 = float(Vn1)
        self.Vn2 = float(Vn2)
        self.Sn = float(Sn)
        self.status = status

        Z_eq = float(Vsc) / 100.0
        R_eq = float(Vr) / 100.0
        X_eq = sqrt(pow(Z_eq, 2) - pow(R_eq, 2))

        # in the transformer base
        self.Z_series = R_eq + 1j* X_eq
        self.Y_shunt = 0.0 # neglect magnetizing branch, could be calculated with Vfe [kW]

    def to_pu(self, Vb1, Vb2, Sb=100):
        '''
            convert impedances to per-unit system
            using off-nominal tap ratios by default as in (glover, 2023) 3.8 - Transformers
                with off-nominal turns ratio
        '''

        a_t = self.Vn1 / self.Vn2
        b = Vb1 / Vb2
        c = a_t / b

        Zb_sys = pow(Vb1, 2) / Sb
        Zb_xfmr = pow(self.Vn1, 2) / self.Sn

        # change to system base
        self.Z_series = self.Z_series * (Zb_xfmr / Zb_sys)
        self.Y_shunt = self.Y_shunt * ((1/Zb_xfmr) / (Zb_sys))

        # off-nominal tap ratios, the minus sign on off diagonal elements are already implemented on get_Y
        self.tap_ratio = [1, c, c, pow(c, 2)]

    def get_Y(self):
        rows = [self.bus_1.uuid, self.bus_1.uuid, self.bus_2.uuid, self.bus_2.uuid]
        cols = [self.bus_1.uuid, self.bus_2.uuid, self.bus_1.uuid, self.bus_2.uuid]
        
        data = [1/self.Z_series + self.Y_shunt/2 if i == j else -1/self.Z_series for i, j in zip(rows,cols)]

        Ydata = [y*ratio for y, ratio in zip(data, self.tap_ratio)]

        return (rows, cols, Ydata)


class Generator:
    def __init__(self, element_id, bus_1, name, Sn, Vn, R_X, xdss_perc, status=True):
        self.element_type = "generator"
        self.element_id = element_id
        self.name = name
        self.bus_1 = bus_1
        self.Sn = float(Sn)
        self.Vn = float(Vn)
        self.xdss = float(xdss_perc)/100
        self.Z_series = (float(R_X) * self.xdss) + 1j* self.xdss
        self.status = status

    def to_pu(self, Vb, Sb=100):
        '''
            convert impedances to per-unit system
        '''
        Zb = pow(Vb, 2) / Sb
        Zb_machine = pow(self.Vn, 2) / self.Sn

        self.Z_series = self.Z_series * (Zb_machine / Zb)

    def get_Y(self):
        rows = [self.bus_1.uuid]
        cols = [self.bus_1.uuid]
        Ydata = [1/self.Z_series if i == j else -1/self.Z_series for i, j in zip(rows,cols)]
        return (rows, cols, Ydata)


class Load:
    def __init__(self, element_id, bus_1, name, P, Q, Vn, status=True):
        '''
            modeled as a constant power
        '''
        self.element_type = "load"
        self.element_id = element_id
        self.name = name
        self.bus_1 = bus_1
        self.P = float(P)
        self.Q = float(Q)
        self.Vn = float(Vn)
        self.status = status

    def to_pu(self, Vb, Sb=100):
        '''
            convert values to per-unit system
        '''
        self.P, self.Q = self.P / Sb, self.Q / Sb
        self.Vn = self.Vn / Vb
        
    def get_Y(self):
        '''
            constant impedance load based on rated values
        '''

        mod_S, arg_S = polar(self.P + 1j* self.Q)
        Z = rect((abs(self.Vn)**2) / mod_S, arg_S)

        return ([self.bus_1.uuid], [self.bus_1.uuid], [1/Z])


class ExternalGrid:
    def __init__(self, bus_1, kV_nom, Rk, Xk, status=True):
        self.element_type = "external_grid"
        self.bus_1 = bus_1
        self.kV_nom = float(kV_nom)
        self.Z_series = (float(Rk) + 1j* float(Xk))
        self.status = status

    def to_pu(self, Vb, Sb=100):
        '''
            convert impedances to per-unit system
        '''
        Zb = pow(Vb, 2) / Sb

        self.Z_series = self.Z_series * (1 / Zb)

    def get_Y(self):
        rows = [self.bus_1.uuid]
        cols = [self.bus_1.uuid]
        Ydata = [1/self.Z_series if i == j else -1/self.Z_series for i, j in zip(rows,cols)]

        return (rows, cols, Ydata)
    

class Transformer3W:
    def __init__(self, element_id, bus_1, bus_2, bus_3, name, 
                 Vn1, Vn2, Vn3, Sn1, Sn2, Sn3, 
                 Vsc12, Vsc23, Vsc31, Vr12, Vr23, Vr31, status=True):
        
        self.element_id = element_id
        self.name = name
        self.bus_1 = bus_1
        self.bus_2 = bus_2
        self.bus_3 = bus_3
        self.Vn1 = float(Vn1)
        self.Vn2 = float(Vn2)
        self.Vn3 = float(Vn3)
        self.Sn1 = float(Sn1)
        self.Sn2 = float(Sn2)
        self.Sn3 = float(Sn3)
        self.status = status

        Z_eq12 = float(Vsc12) / 100.0
        R_eq12 = float(Vr12) / 100.0
        X_eq12 = sqrt(pow(Z_eq12, 2) - pow(R_eq12, 2))

        Z_eq23 = float(Vsc23) / 100.0
        R_eq23 = float(Vr23) / 100.0
        X_eq23 = sqrt(pow(Z_eq23, 2) - pow(R_eq23, 2))

        Z_eq31 = float(Vsc31) / 100.0
        R_eq31 = float(Vr31) / 100.0
        X_eq31 = sqrt(pow(Z_eq31, 2) - pow(R_eq31, 2))

        self.Z1 = 0.5 * ((R_eq12 + 1j* X_eq12) + (R_eq31 + 1j* X_eq31) - (R_eq23 + 1j* X_eq23))
        self.Z2 = 0.5 * ((R_eq12 + 1j* X_eq12) + (R_eq23 + 1j* X_eq23) - (R_eq31 + 1j* X_eq31))
        self.Z3 = 0.5 * ((R_eq23 + 1j* X_eq23) + (R_eq31 + 1j* X_eq31) - (R_eq12 + 1j* X_eq12))

    def to_pu(self, Vb1, Vb2, Vb3, Sb=100):
        '''
            convert impedances to per-unit system
            using off-nominal tap ratios by default as in (glover, 2023) 3.8 - Transformers
                with off-nominal turns ratio
        '''

        V0 = self.Vn1 # the rated voltage of the ficticious node, same as winding 1
        Vb0 = Vb1 # the base voltage of the fictiticous node, same as winding 1

        # between 1 and the ficticious node
        a_t1 = self.Vn1 / V0
        b1 = Vb1 / Vb0
        c1 = a_t1 / b1

        # between 2 and the ficticious node
        a_t2 = self.Vn2 / V0
        b2 = Vb2 / Vb0
        c2 = a_t2 / b2

        # between 3 and the ficticious node
        a_t3 = self.Vn3 / V0
        b3 = Vb3 / Vb0
        c3 = a_t3 / b3

        # base impedances
        Zb1_sys = pow(Vb1, 2) / Sb
        Zb1_xfmr = pow(self.Vn1, 2) / self.Sn1

        Zb2_sys = pow(Vb2, 2) / Sb
        Zb2_xfmr = pow(self.Vn2, 2) / self.Sn2

        Zb3_sys = pow(Vb3, 2) / Sb
        Zb3_xfmr = pow(self.Vn3, 2) / self.Sn3

        # change to system base
        self.Z1 = self.Z1 * (Zb1_xfmr / Zb1_sys)
        self.Z2 = self.Z2 * (Zb2_xfmr / Zb2_sys)
        self.Z3 = self.Z3 * (Zb3_xfmr / Zb3_sys)

        # off-nominal tap ratios, the minus sign on off diagonal elements are already implemented on get_Y
        self.tap_ratio1 = [1, c1, c1, pow(c1, 2)]
        self.tap_ratio2 = [1, c2, c2, pow(c2, 2)]
        self.tap_ratio3 = [1, c3, c3, pow(c3, 2)]

    def get_Y(self):
        '''
            build 3 two-windings transformer into a 4x4 matrix
            reduce to a 3x3 matrix to eliminate the fictiticious node
        '''

        # build 4x4 dense matrix
        size = 4  # buses 1, 2, 3, s
        Y4 = np.zeros((size, size), dtype=complex)

        # get the 2x2 matrix for each winding
        Zs = [self.Z1, self.Z2, self.Z3]
        taps = [self.tap_ratio1, self.tap_ratio2, self.tap_ratio3]

        # build 4x4 matrix
        for i, (Z, tap) in enumerate(zip(Zs, taps)):
            rows = [i, i, size-1, size-1]
            cols = [i, size-1, i, size-1]
            data = [1/Z if i == j else -1/Z for i, j in zip(rows,cols)]
            Ydata = [y*ratio for y, ratio in zip(data, tap)]

            for r, c, d in zip(rows, cols, Ydata):
                Y4[r, c] += d

        # reduce to 3x3 matrix using Kron reduction - eliminate node s
        # partition into external (E) and internal (s)
        ext = [0, 1, 2]
        s = 3
        
        Y_EE = Y4[np.ix_(ext, ext)]
        Y_Es = Y4[np.ix_(ext, [s])]
        Y_sE = Y4[np.ix_([s], ext)]
        Y_ss = Y4[s, s]
        
        Y_red = Y_EE - (Y_Es @ Y_sE) / Y_ss

        # Generate row and column indices
        rows_red, cols_red = np.indices(Y_red.shape)

        # Flatten all
        rows_red = rows_red.ravel()
        cols_red = cols_red.ravel()
        data_red = Y_red.ravel()

        # recover the bus absolute uuid
        wdgs = [self.bus_1, self.bus_2, self.bus_3]
        rows_red = [wdgs[idx].uuid for idx in rows_red]
        cols_red = [wdgs[idx].uuid for idx in cols_red]

        return (rows_red, cols_red, data_red)