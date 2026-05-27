import numpy as np
from scipy.sparse import coo_matrix, csc_matrix, issparse
from scipy.sparse.linalg import splu

class ClassicShortCircuit:

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
    def compute_scc(YBus, V_bus):
        '''
            compute the short circuit current for all buses, for a single snapshot,
            YBus: num_bus x num_bus, contains system admittance matrix (passive + generators)
            V_bus: num_bus x 1, pre-fault bus voltages (p.u.)

            method: compute the impedance matrix ZBus diagonal elements
        '''
        ZBus_diagonal = ClassicShortCircuit.compute_ZBus(YBus)

        assert ZBus_diagonal.shape == V_bus.shape, f"ZBus {ZBus_diagonal.shape} and V_Bus {V_bus.shape} shape mismatch"
        assert np.all(ZBus_diagonal != 0), "ZBus has zero-valued elements"

        return np.divide(V_bus, ZBus_diagonal)

    @staticmethod
    def compose_YSystem(passive_ybus, active_elements):
        '''
            add Yprimitive to Ypassive
        '''

        rows = []
        cols = []
        data = []

        # generators admittances
        for (_, bus_idx), (src, V_pre, S_pre) in active_elements.items():
            # only compute determined elements
            if src.element_type == 'load':
                _, _, d = src.get_Y(V_pre, S_pre)
            elif src.element_type == 'generator':
                _, _, d = src.get_Y()
            elif src.element_type == 'external_grid':
                _, _, d = src.get_Y()
            else:
                continue

            rows.extend([bus_idx])
            cols.extend([bus_idx])
            data.extend(d)

        if not data:
            return passive_ybus  # nothing to add

        delta = coo_matrix((data, (rows, cols)), shape=passive_ybus.shape).tocsr()

        return passive_ybus + delta
    
class ShortCircuit:
    
    @staticmethod
    def build_load_task(bus_idx, data):

        src = data[0]
        V_pre = data[1]
        S_pre = data[2]

        def Y(V):
            # V_terminal = V[bus]
            return src.get_Y(V_pre, S_pre)

        def I(V):
            # V_terminal = V[bus]
            return src.get_I()

        return {"bus_idx": bus_idx, "Y": Y, "I": I}
    
    @staticmethod
    def build_generator_task(bus_idx, data):

        src = data[0]
        V_pre = data[1]
        S_pre = data[2]

        def Y(V):
            # V_terminal = V[bus]
            return src.get_Y()

        def I(V):
            # V_terminal = V[bus]
            return src.get_I(V_pre, S_pre)

        return {"bus_idx": bus_idx, "Y": Y, "I": I}

    @staticmethod 
    def build_full_converter_task(bus_idx, data):

        src = data[0]
        V_pre = data[1]
        S_pre = data[2]

        def Y(V):
            # V_terminal = V[bus]
            return src.get_Y()

        def I(V):
            V_terminal = V[bus_idx]
            return src.get_I(V_terminal, V_pre, S_pre)

        return {"bus_idx": bus_idx, "Y": Y, "I": I}
    
    @staticmethod
    def build_external_grid_task(bus_idx, data):

        src = data[0]
        V_pre = data[1]
        S_pre = data[2]

        def Y(V):
            # V_terminal = V[bus]
            return src.get_Y()

        def I(V):
            # V_terminal = V[bus]
            return src.get_I(V_pre, S_pre)

        return {"bus_idx": bus_idx, "Y": Y, "I": I}
    
    @staticmethod
    def SCC_tasks(active_elements):

        tasks = {}

        for (name, bus_idx), element_data in active_elements.items():

            element_type = element_data[0].element_type

            if element_type == "load":
                tasks[(name, bus_idx)] = ShortCircuit.build_load_task(bus_idx, element_data)

            elif element_type == "generator":
                tasks[(name, bus_idx)] = ShortCircuit.build_generator_task(bus_idx, element_data)

            elif element_type == "full_converter":
                tasks[(name, bus_idx)] = ShortCircuit.build_full_converter_task(bus_idx, element_data)

            elif element_type == "external_grid":
                tasks[(name, bus_idx)] = ShortCircuit.build_external_grid_task(bus_idx, element_data)

        return tasks

    @staticmethod
    def compute_residual(V, tasks, Y_passive_fault):

        Y_SCC = Y_passive_fault.copy()
        I_inj = np.zeros_like(V)
        rows, cols, data = [], [], []

        for t in tasks.values():

            bus_idx = t["bus_idx"]

            _, _, Y_prim =  t["Y"](V)
            rows.extend([bus_idx])
            cols.extend([bus_idx])
            data.extend(Y_prim)

            I_inj[bus_idx] += t["I"](V)

        Y_SCC += csc_matrix((data, (rows, cols)), shape=Y_SCC.shape)

        return Y_SCC @ V - I_inj

    @staticmethod
    def compute_jacobian(V, tasks, Y_passive_fault, dV=1e-6):

        n = len(V)
        f0 = ShortCircuit.compute_residual(V, tasks, Y_passive_fault)

        J = np.zeros((n, n), dtype=complex)

        for j in range(n):

            Vp = V.copy()
            Vp[j] += dV

            f1 = ShortCircuit.compute_residual(Vp, tasks, Y_passive_fault)

            J[:, j] = (f1 - f0) / dV

        return J

    @staticmethod
    def SCC_NR(fault_bus_idx, V_complex, passive_YBus, active_elements, max_iter=100, tol=1e-6, zf=1e-6):
        '''
            ThetaV: the initial guess. it is the power flow solution
            Y_SCC -> csc sparse: contain all impedances. passive network, generators equivalent and load equivalents
            lin_sources: contains the linear sources elements, i.e. synchronous generators
            nonlin_sources: contains the non linear sources elements, i.e. full converters
        '''
        convergence = False

        # initial voltages vector: power flow solution
        V_fault = V_complex.copy()

        # add fault impedance
        Y_passive_fault = passive_YBus.tocsc()
        Y_passive_fault += csc_matrix(([1/zf], ([fault_bus_idx], [fault_bus_idx])), shape=Y_passive_fault.shape)

        residuals = []
        iteration = 0
        while iteration <= max_iter:

            # generate taks with argments for computing Y and I for each active element
            tasks = ShortCircuit.SCC_tasks(active_elements)

            # compute residual
            f = ShortCircuit.compute_residual(V_fault, tasks, Y_passive_fault)
            residuals.append(f)
            # print(f"iter {iteration+1}: ||f|| = {np.linalg.norm(f):.6e}")

            if max(abs(f)) < tol:
                convergence = True
                break

            # compute jacobian
            J = ShortCircuit.compute_jacobian(V_fault, tasks, Y_passive_fault)

            # dV = spsolve(J, -f)
            dV = np.linalg.solve(J, -f)

            # fine tune the damping parameter to help convergence
            alpha = 1.0
            f_norm = np.linalg.norm(f)
            while np.linalg.norm(ShortCircuit.compute_residual(V_fault + alpha * dV, tasks, Y_passive_fault)) > f_norm:
                alpha *= 0.5
                if alpha < 1e-4:
                    break

            V_fault += alpha*dV # damping factor
            iteration += 1

        if not convergence:
            print(f'\t\t\t> short circuit calculation did not converged in {max_iter} iterations for fault in bus {fault_bus_idx}')
            results = np.column_stack(residuals)
            import matplotlib.pyplot as plt
            plt.plot(np.abs(results).T)
            plt.show()
            raise RuntimeError("Short circuit did not converged. Interrupting simulation.")

        return V_fault[fault_bus_idx] / zf

    @staticmethod
    def compute_dIdV(nonlinear_sources, V, ThetaV, dV=1e-6):
        '''
            numerical computation of the jacobian. for voltage dependent sources
            V: complex value of voltage under fault condition
            ThetaV: complex value of voltage before fault
        '''
        dI = {}
        for (_, bus_idx), (src, S_src) in nonlinear_sources.items():
            f0 = src.get_I(V[bus_idx], ThetaV[bus_idx], S_src)
            f1 = src.get_I(V[bus_idx] + dV, ThetaV[bus_idx], S_src)
            dI[bus_idx] = dI.get(bus_idx, 0) + (f1 - f0) / dV
            
        return dI