import os
import numpy as np
import csv
import cmath
from dataclasses import dataclass
from typing import Callable
import json

from models.CustomNetwork import CustomNetwork
from models.PowerFlow import PowerFlow
from models.ShortCircuit import ShortCircuit as SC
from models.ShortCircuit import ClassicShortCircuit as CSC

cases_dir = os.path.join(os.path.dirname(__file__), 'cases')
report_dir = os.path.join(os.path.dirname(__file__), 'reports')
meta_dir = os.path.join(os.path.dirname(__file__), 'reports', 'meta_files')

@dataclass
class Scenario:
    name: str
    file: str
    solver: Callable
    pre_pf_setup: Callable = lambda net: None
    fault_setup: Callable = lambda net: None
    v_mag: float | None = None
    v_ang: float | None = None
    file_out: str = "" # dont give file out name manually to keep the standarization

    def __post_init__(self):
        if not self.file_out:
            self.file_out = f"{self.name}.csv"


def setup_equal_scale_load(factor):
    ''' scale all load equally '''
    def setup(network):
        for load in network.loads.values():
            load.P *= factor
            load.Q *= factor
    return setup

def setup_unequal_scale_loads(factors):
    ''' scale all load unequally: each one have its factor '''
    def setup(network):
        for load, factor in zip(network.loads.values(), factors):
            load.P *= factor
            load.Q *= factor
    return setup

def setup_change_all_loads_status_to(status):
    def setup(network):
        for element in network.loads.values():
            element.status=status
    return setup

def setup_change_all_converters_status_to(status):
    def setup(network):
        for element in network.full_converters.values():
            element.status=status
    return setup

def setup_change_all_generators_status_to(status):
    def setup(network):
        for element in network.generators.values():
            element.status=status
    return setup

def setup_change_all_external_grids_status_to(status):
    def setup(network):
        for element in network.external_grids.values():
            element.status=status
    return setup

def setup_element_status(element_name, status):
    def setup(network):
        network.change_element_status(element_name, status)
    return setup

def setup_change_generator_P(gen_full_name, P):
    ''' scale all load equally '''
    def setup(network):
        network.generators[gen_full_name].P = P
    return setup

def setup_change_generator_Z(gen_full_name, Z):
    ''' scale all load equally '''
    def setup(network):
        network.generators[gen_full_name].Z_series = Z
    return setup

def compose(*fns):
    def setup(network):
        for fn in fns:
            fn(network)
    return setup


def classic(s, save_csv=True):
    
    # extract scenario parameters
    case_file = s.file
    file_out = s.file_out
    pre_pf_setup = s.pre_pf_setup
    fault_setup = s.fault_setup
    v_mag = s.v_mag
    v_ang = s.v_ang
    
    ''' here i implement the Zbus method, for linear SCC calculation (only SG) '''
    network = CustomNetwork(os.path.join(cases_dir, case_file))
    network.create_network()
    n_buses = len(network.buses)

    ''' pre POWER FLOW setup: which will affect both POWER FLOW and FAULT '''
    pre_pf_setup(network)

    network.build_ybus() # this is valid ONLY if the passive network topology is fixed

    # must be known beforehand
    passive_ybus = network.YBus # assumption of a fixed topology
    
    pfSolver = PowerFlow()

    # one time power flow
    Theta, V = pfSolver.solve_power_flow(network)

    # get bus voltages from `SCADA`
    mag = np.full(n_buses, v_mag) if v_mag is not None else V # to define a fixed magnitude
    ang = np.full(n_buses, v_ang) if v_ang is not None else Theta # to define a fixed angle
    V_complex = np.array([v * np.exp(1j * t) for t, v in zip(ang, mag)])

    active_element_flow = pfSolver.get_active_elements_flow(network, np.concatenate((Theta, V)))

    # collect data for writing CSV, this captures the pre fault setup
    caseData, totals = pfSolver.power_flow_summary(network, np.concatenate((Theta, V)))

    ''' pre FAULT setup: to not consider some element in fault calculation '''
    fault_setup(network)

    active_element_status = pfSolver.get_active_element_status(network)

    # active elements => (name, bus_idx): (element, v_pre, s_pre)
    if (v_mag is not None) or (v_ang is not None):
        # if one of the parameters is overwriten, flat start
        active_element_flow = {k: 0+1j*0 for k, _ in active_element_flow.items()}
    active_elements = network.get_active_elements(V_complex, active_element_flow, active_element_status)

    # system variables
    system_YBus = CSC.compose_YSystem(passive_ybus, active_elements)

    # estimate short circuit
    ISCC_bus = CSC.compute_scc(system_YBus, V_complex)
    
    # export results
    for i, r in enumerate(caseData):
        r.extend([abs(ISCC_bus[i]), cmath.phase(ISCC_bus[i])*180/cmath.pi])

    # write CSV
    if save_csv:
        with open(os.path.join(report_dir, file_out), "w", newline="") as f:
            writer = csv.writer(f)

            # header
            writer.writerow([
                "bus","pre_fault_V_mag","pre_fault_V_ang_deg",
                "P_net","Q_net","P_gen","Q_gen", "P_conv", "Q_conv",
                "P_load","Q_load","P_shunt","Q_shunt",
                "I_SCC_mag", "I_SCC_and_deg"
            ])

            writer.writerows(caseData)

        meta_out = file_out.removesuffix(".csv") + "_meta.json"
        with open(os.path.join(meta_dir, meta_out), "w") as f:
            json.dump(totals, f, indent=2)

    return caseData


def iterative(s, save_csv=True):

    # extract scenario parameters
    case_file = s.file
    file_out = s.file_out
    pre_pf_setup = s.pre_pf_setup
    fault_setup = s.fault_setup
    v_mag = s.v_mag
    v_ang = s.v_ang

    # instantiate network elements and parse data from JSON
    network = CustomNetwork(os.path.join(cases_dir, case_file))
    network.create_network()
    n_buses = len(network.buses)

    ''' pre POWER FLOW setup: which will affect both POWER FLOW and FAULT '''
    pre_pf_setup(network)

    # build passive YBus
    network.build_ybus() # this is valid ONLY if the passive network topology is fixed

    # must be known beforehand
    passive_ybus = network.YBus # assumption of a fixed topology

    # solve power flow
    pfSolver = PowerFlow()
    Theta, V = pfSolver.solve_power_flow(network)

    '''
        SCADA interface.
        data must be acquired from pfSolver() class

        Data:
            1) Complex bus voltage (V)
            2) Complex power (S)
            3) Facilities breaker status
    '''
    # get bus voltages from `SCADA`
    mag = np.full(n_buses, v_mag) if v_mag is not None else V # to define a fixed magnitude
    ang = np.full(n_buses, v_ang) if v_ang is not None else Theta # to define a fixed angle
    V_complex = np.array([v * np.exp(1j * t) for t, v in zip(ang, mag)])

    # get elements complex power from `SCADA`
    active_element_flow = pfSolver.get_active_elements_flow(network, np.concatenate((Theta, V)))

    # collect data for writing CSV, this captures the pre fault setup
    caseData, totals = pfSolver.power_flow_summary(network, np.concatenate((Theta, V)))

    ''' pre FAULT setup: to not consider some element in fault calculation '''
    fault_setup(network)

    # get elements breaker status from `SCADA``
    active_element_status = pfSolver.get_active_element_status(network)

    # active elements => (name, bus_idx): (element, v_pre, s_pre)
    if (v_mag is not None) or (v_ang is not None):
        # if one of the parameters is overwriten, flat start
        active_element_flow = {k: 0+1j*0 for k, _ in active_element_flow.items()}
    active_elements = network.get_active_elements(V_complex, active_element_flow, active_element_status)

    # run short circuit for fault at each bus of the network, one at a time
    ISCC_bus = []
    print('\t\tSolving Short-circuit using Newton-Raphson method...')
    for bus in network.buses.keys():
        i_scc = SC.SCC_NR(network.idx[bus], V_complex, passive_ybus, active_elements)
        ISCC_bus.append(i_scc)

    for i, r in enumerate(caseData):
        r.extend([abs(ISCC_bus[i]), cmath.phase(ISCC_bus[i])*180/cmath.pi])

    # write CSV
    if save_csv:
        with open(os.path.join(report_dir, file_out), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "bus","pre_fault_V_mag","pre_fault_V_ang_deg",
                "P_net","Q_net","P_gen","Q_gen", "P_conv", "Q_conv",
                "P_load","Q_load","P_shunt","Q_shunt",
                "I_SCC_mag", "I_SCC_and_deg"
            ])

            writer.writerows(caseData)
        
        meta_out = file_out.removesuffix(".csv") + "_meta.json"
        with open(os.path.join(meta_dir, meta_out), "w") as f:
            json.dump(totals, f, indent=2)
    
    return caseData, totals


def iterative_timeseries(scenarios: list[Scenario], file_out):
    results = []
    for s in scenarios:
        print(f'\t... solving {s.name}')
        result, _ = iterative(s, save_csv=False)
        results.append(result)
    
    with open(os.path.join(report_dir, file_out), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "step", "scenario",
            "bus", "pre_fault_V_mag", "pre_fault_V_ang_deg",
            "P_net", "Q_net", "P_gen", "Q_gen", "P_conv", "Q_conv",
            "P_load", "Q_load", "P_shunt", "Q_shunt",
            "I_SCC_mag", "I_SCC_ang_deg"
        ])
        for step, (s, results) in enumerate(zip(scenarios, results)):
            for row in results:
                writer.writerow([step, s.name, *row])

SCENARIOS = [
    Scenario("CASE_0", '14bus_modified.json', solver=iterative),
    Scenario("CASE_1", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g2', True))),
    Scenario("CASE_2", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g3', True))),
    Scenario("CASE_3", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g6', True))),
    Scenario("CASE_4", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g8', True))),
    Scenario("CASE_5", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_element_status('generator.g2', False)),
    Scenario("CASE_6", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_element_status('generator.g8', False)),
    Scenario("2-1", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_equal_scale_load(0.3)),
    Scenario("2-2", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_equal_scale_load(1.7)),
    Scenario("2-3", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_element_status('load.load 3', False)),
    Scenario("2-4", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_element_status('line.line 45', False)),
    Scenario("3-0", '14bus_modified.json', solver=iterative, pre_pf_setup=setup_change_all_generators_status_to(True)),
    Scenario("3-1", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        setup_change_generator_P('generator.g2', 0.4-0.1*0.9),
        setup_change_generator_P('generator.g12', 0.06-0.06*0.9),
        setup_change_generator_P('generator.g13', 0.07-0.07*0.9),
        setup_change_generator_P('generator.g14', 0.08-0.08*0.9),
    )),
    Scenario("3-2", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        setup_element_status('generator.g2', False),
        setup_element_status('generator.g12', False),
        setup_element_status('generator.g13', False),
        setup_element_status('generator.g14', False),
    )),
    Scenario("3-3", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False),
        setup_element_status('generator.g1', True),
        setup_change_generator_Z('generator.g1', float("inf")),
        setup_change_all_converters_status_to(True),
    )),
    Scenario("4-0", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
    )),
    Scenario("4-1", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
    ), fault_setup=setup_change_all_loads_status_to(False)),
    Scenario("4-2A", '14bus_modified_conv400.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True))),
    Scenario("4-2B", '14bus_modified_conv400.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
    ), fault_setup=setup_change_all_converters_status_to(False)),
    Scenario("4-3A", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        setup_change_all_external_grids_status_to(True)
    )),
    Scenario("4-3B", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        setup_change_all_external_grids_status_to(True)
    ), fault_setup=setup_element_status('external_grid.External Grid 2', False)),
    Scenario("4-4", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        ), 
        v_mag=1.05, v_ang=0.0),
    Scenario("4-4_095", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        ), 
        v_mag=0.95, v_ang=0.0),
    Scenario("4-4_100", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        ), 
        v_mag=1.00, v_ang=0.0),
    Scenario("4-4_110", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        ), 
        v_mag=1.10, v_ang=0.0),
    Scenario("4-5", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
        setup_change_all_generators_status_to(True),
        setup_change_all_converters_status_to(True),
        ), 
        v_mag=1.05, 
        v_ang=0.0, 
        fault_setup=compose(
            setup_change_all_loads_status_to(False),
            setup_change_all_converters_status_to(False)
            )
        ),
    Scenario("classic_CASE_0", '14bus_modified.json', solver=classic),
    Scenario("classic_CASE_1", '14bus_modified.json', solver=classic, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g2', True))),
    Scenario("classic_CASE_2", '14bus_modified.json', solver=classic, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g3', True))),
    Scenario("classic_CASE_3", '14bus_modified.json', solver=classic, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g6', True))),
    Scenario("classic_CASE_4", '14bus_modified.json', solver=classic, pre_pf_setup=compose(
        setup_change_all_generators_status_to(False), setup_element_status('generator.g1', True), setup_element_status('generator.g8', True))),
    Scenario("classic_CASE_5", '14bus_modified.json', solver=classic, pre_pf_setup=setup_element_status('generator.g2', False)),
    Scenario("classic_CASE_6", '14bus_modified.json', solver=classic, pre_pf_setup=setup_element_status('generator.g8', False)),
    Scenario("classic_4-5", '14bus_modified.json', solver=classic, pre_pf_setup=compose(
            setup_change_all_generators_status_to(True),
            setup_change_all_converters_status_to(True),
        ), 
        v_mag=1.05, 
        v_ang=0.0, 
        fault_setup=compose(
            setup_change_all_loads_status_to(False),
            setup_change_all_converters_status_to(False)
            )
        ),
]

if __name__ == '__main__':

    # # single scenario

    # iterative(Scenario("4-0", '14bus_modified.json', pre_pf_setup=compose(
    #     setup_change_all_generators_status_to(True),
    #     setup_change_all_converters_status_to(True),
    # )),)

    # run scenarios
    print('solving collection of scenarios...')
    for s in SCENARIOS:
        print(f'\n\tsolving {s.name} for {s.file} using {s.solver.__name__} method')
        s.solver(s)

    # get load scaling factor from BZN|SE2 markov chain model
    data = np.genfromtxt("load_profile.csv", delimiter=",", names=True)

    hours = data["hour"].astype(int)
    scale_cols = [c for c in data.dtype.names if c.startswith("seq_")]
    scales = np.column_stack([data[c] for c in scale_cols])  # shape (24, N)

    TIMESERIES = []
    for i in range(len(hours)):
        # normal operation outside noon, converters are off
        # 0-8, 16-23
        if not (9 <= i <= 15): 
            TIMESERIES.append(Scenario(f"{i}", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
                setup_unequal_scale_loads(scales[i]),
                setup_change_all_generators_status_to(True),
            )))
        # converters ramp up/down, reduce SG production
        # 9, 15
        elif not (10 <= i <= 14):
            TIMESERIES.append(
                Scenario(f"{i}", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
                    setup_unequal_scale_loads(scales[i]),
                    setup_change_all_generators_status_to(True),
                    setup_change_all_converters_status_to(True),
                    setup_change_generator_P('generator.g2', 0.4-0.1*0.9),
                    setup_change_generator_P('generator.g12', 0.06-0.06*0.9),
                    setup_change_generator_P('generator.g13', 0.07-0.07*0.9),
                    setup_change_generator_P('generator.g14', 0.08-0.08*0.9),
                )))
        # 10, 11, 13, 14
        elif not (11 < i < 13):
            TIMESERIES.append(
                Scenario(f"{i}", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
                    setup_unequal_scale_loads(scales[i]),
                    setup_change_all_generators_status_to(True),
                    setup_change_all_converters_status_to(True),
                    setup_change_generator_P('generator.g2', 0.1),
                    setup_element_status('generator.g12', False),
                    setup_element_status('generator.g13', False),
                    setup_element_status('generator.g14', False),
                )))
        # converter at peak production, turn off generators
        else: 
            TIMESERIES.append(
                Scenario(f"{i}", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
                    setup_unequal_scale_loads(scales[i]),
                    setup_change_all_generators_status_to(True),
                    setup_change_all_converters_status_to(True),
                    setup_element_status('generator.g2', False),
                    setup_element_status('generator.g12', False),
                    setup_element_status('generator.g13', False),
                    setup_element_status('generator.g14', False),
                )))

    # run timeseries (ordered collection of scenarios)
    print('solving timeseries using iterative method.')
    file_out = 'timeseries_14bus.csv'
    snapshots = iterative_timeseries(TIMESERIES, file_out)
    print()
    

    ''' random turning off of generators '''
    import random
    random.seed(42)

    # Define the pool of possible setups
    possible_setups = [
        setup_element_status('generator.g2', False),
        setup_element_status('generator.g3', False),
        setup_element_status('generator.g6', False),
        setup_element_status('generator.g8', False),
        setup_element_status('generator.g12', False),
        setup_element_status('generator.g13', False),
        setup_element_status('generator.g14', False),
    ]

    N = 24  # number of random scenarios

    RANDOM_TIMESERIES = []
    for i in range(N):

        # Fixed setups that always apply
        base_setups = [
            setup_unequal_scale_loads(scales[i]),
            setup_change_all_generators_status_to(True),
            setup_change_all_converters_status_to(True),
        ]

        # Pick a random subset (0 to all elements)
        k = random.randint(0, len(possible_setups))
        sampled = random.sample(possible_setups, k)

        RANDOM_TIMESERIES.append(
            Scenario(f"{i}", '14bus_modified.json', solver=iterative, pre_pf_setup=compose(
                *base_setups,
                *sampled,
            ))
        )

    # run timeseries (ordered collection of scenarios)
    print('solving timeseries using iterative method.')
    file_out = 'random_timeseries_14bus.csv'
    snapshots = iterative_timeseries(RANDOM_TIMESERIES, file_out)
    print()
