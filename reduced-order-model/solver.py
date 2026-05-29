import numpy as np
from scipy.sparse import issparse
from scipy.sparse.linalg import splu


class Solver:

    @staticmethod
    def compute_ZBus(YBus):
        '''
            compute the bus impedance matrix ZBus from the admittance matrix YBus
            method: compute only diagonal elements with LU decomposition
        '''
        if not issparse(YBus):
            raise TypeError("YBus must be a scipy sparse matrix")

        N = YBus.shape[0]
        ZBus_diagonal = np.zeros(N, dtype=complex)

        # Convert once to CSC (required by splu)
        YBus_csc = YBus.tocsc()

        # LU factorization (done once)
        lu = splu(YBus_csc)

        # Solve N linear systems (unit vectors)
        for i in range(N):
            b = np.zeros(N, dtype=complex)
            b[i] = 1.0
            x = lu.solve(b)
            ZBus_diagonal[i] = x[i]

        return ZBus_diagonal

    @staticmethod
    def compute_scc(YBus, mod_V):
        '''
            compute the short circuit current for all buses, for a single snapshot,
            YBus: num_bus x num_bus, contains system admittance matrix (passive + generators)
            V_bus: scalar, fixed pre-fault value

            method: compute the impedance matrix ZBus diagonal elements
        '''
        ZBus_diagonal = Solver.compute_ZBus(YBus)
        V_bus = np.ones_like(ZBus_diagonal) * (mod_V + 1j*0) # angle 0

        assert np.all(ZBus_diagonal != 0), "ZBus has zero-valued elements"

        return np.divide(V_bus, ZBus_diagonal)
