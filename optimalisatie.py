from abc import ABC, abstractmethod
import copy
import random
from time import time
from datetime import datetime
from numpy.random import RandomState
import pulp
import alns
import matplotlib.pyplot as plt
from .synchrotool import Planning, Container


class Methode(ABC):

    def __init__(self, planning: Planning):
        self.planning = planning

    @abstractmethod
    def solve(self):
        pass


class LinearProgramming(Methode):

    def __init__(self, planning: Planning):
        Methode.__init__(self, planning)
        self.pulp = pulp.LpProblem(planning.naam, pulp.LpMinimize)
        self._x = {}  # binary variable x to state leg i is chosen by container k or not
        self._y = {}  # binary variable y to state two adjacent legs are both used by container k or not

    def _decision_variables(self):
        for k in range(len(self.planning.containers)):
            for l1 in self.planning.legs:
                self._x[k, l1.id] = pulp.LpVariable("x_(%s_%s)" % (k, l1.id), cat=pulp.LpBinary)
                for l2 in self.planning.legs:
                    if l1.naar == l2.van:
                        self._y[k, l1.id, l2.id] = pulp.LpVariable("y_(%s_%s_%s)" % (k, l1.id, l2.id), cat=pulp.LpBinary)

    def __aantal_uren(self, t1: datetime, t2: datetime):
        # aantal uren tussen t1 en t2
        return (t2 - t1).total_seconds() / 3600.0

    def _objective_function(self):
        self.pulp += pulp.lpSum([self._x[c.id, l.id] * (l.prijs(c.containertype)
                                                        + l.emissie(c.containertype) * c.emissiefactor)  # f_c + f_e
                                 for l in self.planning.legs for c in self.planning.geef_containers()]) + \
                     pulp.lpSum([self._x[c.id, l.id] * (c.boete_te_vroeg *
                                                        max(self.__aantal_uren(l.aankomst, c.min_levertijd), 0) +  # f_early
                                                        c.boete_te_laat *
                                                        max(self.__aantal_uren(c.max_levertijd, l.aankomst), 0))   # f_late
                                 for l in self.planning.legs for c in self.planning.geef_containers() if c.naar == l.naar])

    def _leg_constraints(self):
        for c in self.planning.geef_containers():
            for v in self.planning.locaties:
                rhs = -1 if v == c.van else 1 if v == c.naar else 0
                self.pulp += pulp.lpSum([self._x[c.id, l.id] for l in self.planning.legs if l.naar == v]) - \
                             pulp.lpSum([self._x[c.id, l.id] for l in self.planning.legs if l.van  == v]) == rhs

    def _capacity_constraints(self):
        for s in self.planning.containertypes:
            for l in self.planning.legs:
                self.pulp += l.aantal(s) - \
                             pulp.lpSum([self._x[c.id, l.id] for c in self.planning.geef_containers()
                                         if c.containertype == s]) >= 0

    def _time_constraints(self):
        for c in self.planning.geef_containers():
            for l1 in self.planning.legs:
                # departure
                if c.van == l1.van:
                    self.pulp += self._x[c.id, l1.id] * (c.min_ophaaltijd - l1.checkin).total_seconds() <= 0
                    self.pulp += self._x[c.id, l1.id] * (l1.checkin - c.max_ophaaltijd).total_seconds() <= 0
                # arrival
                if c.naar == l1.naar:
                    self.pulp += self._x[c.id, l1.id] * (l1.aankomst - c.uiterste_levertijd).total_seconds() <= 0
                # time windows
                for l2 in self.planning.legs:
                    if l1.naar == l2.van:
                        self.pulp += self._y[c.id, l1.id, l2.id] * (l1.aankomst - l2.checkin).total_seconds() <= 0
                        self.pulp += (self._x[c.id, l1.id] + self._x[c.id, l2.id] - self._y[c.id, l1.id, l2.id] - 1.5) <= 0
                        self.pulp += (2 * self._y[c.id, l1.id, l2.id] - self._x[c.id, l1.id] - self._x[c.id, l2.id] - 0.5) <= 0

    def solve(self):
        start = time()
        self._decision_variables()
        self._objective_function()
        self._leg_constraints()
        self._capacity_constraints()
        self._time_constraints()
        self.pulp.solve()
        self._get_solution()
        print("Elapsed time:", round(time() - start, 2), 'sec')
        print("Solution status:", pulp.LpStatus[self.pulp.status])
        print("Minimal cost:", pulp.value(self.pulp.objective))

    def _get_solution(self):
        for c in self.planning.geef_containers():
            traject = []
            for l in self.planning.legs:
                if self._x[c.id, l.id].value() == 1:
                    legcapaciteit = l.capaciteiten[c.containertype]
                    traject.append(legcapaciteit)
            self.planning.voeg_traject_toe(c.id, *sorted(traject))


class MaakContainerTraject:

    def __init__(self, planning: Planning, container: Container = None):
        self.planning = planning
        self.container = container

    def maak_greedy_traject(self, van_naar=True):
        # van_naar = True: traject wordt geconstrueerd van container.van naar container.naar
        # van_naar = False: traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        def selecteer(capaciteiten):
            return min(capaciteiten, key=capaciteiten.get)
        if van_naar:
            return self.__maak_traject_van_naar(selecteer)
        else:
            return self.__maak_traject_naar_van(selecteer)

    def maak_random_traject(self, van_naar=True):
        # van_naar = True: traject wordt geconstrueerd van container.van naar container.naar
        # van_naar = False: traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        def selecteer(capaciteiten):
            return random.choice([capaciteit for capaciteit in capaciteiten])
        if van_naar:
            return self.__maak_traject_van_naar(selecteer)
        else:
            return self.__maak_traject_naar_van(selecteer)

    def __schat_totale_kost(self, capaciteiten, van_naar=True):
        capaciteiten = {capaciteit: self.planning.adhoc_legs.schat_totale_kost(capaciteit, self.container, van_naar)
                        for capaciteit in capaciteiten}
        capaciteiten = {capaciteit: kost for capaciteit, kost in capaciteiten.items() if kost is not None}
        return capaciteiten

    def __maak_traject_van_naar(self, selecteer):
        # traject wordt geconstrueerd van container.van naar container.naar
        # selecteer is een functie die een LegCapaciteit object retourneert uit een input list van legcapaciteiten
        traject = []
        locaties = set(self.planning.verladers + self.planning.empty_depots)  # alleen terminals alles tussenstop toegestaan!
        if self.container.van not in locaties:
            locaties.add(self.container.van)  # voeg startlocatie toe aan locaties die verboden zijn
        if self.container.naar in locaties:
            locaties.remove(self.container.naar)  # verwijder eindlocatie uit locaties die verboden zijn
        capaciteiten = [lc for lc in self.planning.legcapaciteiten
                        if lc.is_mogelijk_begin(self.container) and lc.leg.naar not in locaties]  # alle mogelijke startcapaciteiten
        capaciteiten = self.__schat_totale_kost(capaciteiten)
        if not capaciteiten:  # geen startcapaciteiten: maak een adhoc capaciteit voor het ganse traject
            capaciteit = self.planning.adhoc_legs.maak_leg(self.container)
            if capaciteit is not None:
                traject.append(capaciteit)
            return traject
        while True:
            capaciteit = selecteer(capaciteiten)
            traject.append(capaciteit)
            if capaciteit.leg.naar == self.container.naar:  # leg eindigt in eindbestemming: traject is compleet
                return traject
            else:
                locaties.add(capaciteit.leg.naar)  ###
                capaciteiten = [lc for lc in self.planning.legcapaciteiten
                                if lc.komt_na(capaciteit) and lc.leg.naar not in locaties]  # alle mogelijke volgende capaciteiten ###
                capaciteiten = self.__schat_totale_kost(capaciteiten)
                if not capaciteiten:  # geen capaciteit gevonden: creëer adhoc capaciteit tot eindbestemming
                    capaciteit = None
                    while capaciteit is None and traject:
                        capaciteit = self.planning.adhoc_legs.maak_leg_na_leg(traject[-1].leg, self.container)
                        if capaciteit is None:  # geen adhoc capaciteit mogelijk
                            lc = traject.pop()  # verwijder laatste capaciteit uit traject en probeer opnieuw  ###
                            locaties.remove(lc.leg.naar)  ###
                    if capaciteit is None:
                        capaciteit = self.planning.adhoc_legs.maak_leg(self.container)
                    if capaciteit is not None:
                        traject.append(capaciteit)
                    return traject

    def __maak_traject_naar_van(self, selecteer):
        # traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        # selecteer is een functie die een LegCapaciteit object retourneert uit een input list van legcapaciteiten
        traject = []
        locaties = set(self.planning.verladers + self.planning.empty_depots)  # alleen terminals alles tussenstop toegestaan!
        if self.container.van in locaties:
            locaties.remove(self.container.van)  # verwijder startlocatie uit locaties die verboden zijn
        if self.container.naar not in locaties:
            locaties.add(self.container.naar)  # voeg eindlocatie toe aan locaties die verboden zijn
        capaciteiten = [lc for lc in self.planning.legcapaciteiten
                        if lc.is_mogelijk_einde(self.container) and lc.leg.van not in locaties]  # alle mogelijke eindcapaciteiten
        capaciteiten = self.__schat_totale_kost(capaciteiten)
        if not capaciteiten:  # geen eindcapaciteiten: maak een adhoc capaciteit voor het ganse traject
            capaciteit = self.planning.adhoc_legs.maak_leg(self.container)
            if capaciteit is not None:
                traject.append(capaciteit)
            return traject
        while True:
            capaciteit = selecteer(capaciteiten)
            traject.append(capaciteit)
            if capaciteit.leg.van == self.container.van:  # leg start in startbestemming: traject is compleet
                traject.reverse()
                return traject
            else:
                locaties.add(capaciteit.leg.van)  ###
                capaciteiten = [lc for lc in self.planning.legcapaciteiten
                                if lc.komt_voor(capaciteit) and lc.leg.van not in locaties]  # alle mogelijke voorgaande capaciteiten ###
                capaciteiten = self.__schat_totale_kost(capaciteiten)
                if not capaciteiten:  # geen capaciteit gevonden: creëer adhoc capaciteit tot startbestemming
                    capaciteit = None
                    while capaciteit is None and traject:
                        capaciteit = self.planning.adhoc_legs.maak_leg_voor_leg(traject[-1].leg, self.container)
                        if capaciteit is None:  # geen adhoc capaciteit mogelijk
                            lc = traject.pop()  # verwijder laatste capaciteit uit traject en probeer opnieuw ###
                            locaties.remove(lc.leg.van)  ###
                    if capaciteit is None:
                        capaciteit = self.planning.adhoc_legs.maak_leg(self.container)
                    if capaciteit is not None:
                        traject.append(capaciteit)
                    traject.reverse()
                    return traject


class PlanningState(alns.State):

    def __init__(self, planning: Planning, degree_of_destruction=0.25):
        self.planning = planning
        self.degree_of_destruction = degree_of_destruction

    def objective(self):
        return self.planning.geef_totale_kost() / 1000.0

    def aantal_te_verwijderen_trajecten(self):
        return int(len(self.planning.trajecten) * self.degree_of_destruction)


def worst_removal(state: PlanningState, random_state):
    worst = sorted(list(range(len(state.planning.containers))),
                   key=lambda container_id: state.planning.kosten[container_id], reverse=True)
    destroyed = copy.deepcopy(state)
    for i in range(state.aantal_te_verwijderen_trajecten()):
        destroyed.planning.verwijder_traject(worst[i])
    return destroyed


def random_removal(state: PlanningState, random_state):
    destroyed = copy.deepcopy(state)
    for i in random_state.choice(len(state.planning.trajecten),
                                 state.aantal_te_verwijderen_trajecten(), replace=False):
        destroyed.planning.verwijder_traject(i)
    return destroyed


def __repair(state: PlanningState, random_state, method: str, van_naar=True):
    maak_traject = MaakContainerTraject(state.planning)
    te_plannen = list(state.planning.te_plannen)
    random_state.shuffle(te_plannen)
    for i in te_plannen:
        maak_traject.container = state.planning.geef_container_object(i)
        func = getattr(maak_traject, method)
        traject = func(van_naar)
        state.planning.voeg_traject_toe(i, *traject)
    return state


def greedy_repair(state: PlanningState, random_state):
    return __repair(state, random_state, 'maak_greedy_traject')


def random_repair(state: PlanningState, random_state):
    return __repair(state, random_state, 'maak_random_traject')


def reversed_greedy_repair(state: PlanningState, random_state):
    return __repair(state, random_state, 'maak_greedy_traject', False)


def reversed_random_repair(state: PlanningState, random_state):
    return __repair(state, random_state, 'maak_random_traject', False)


class ALNS(Methode):

    def __init__(self, planning: Planning, degree_of_destruction: float = 0.25, weights: list = None,
                 operator_decay: float = 0.8, iterations: int = 10000, seed: int = None, collect_stats=True):
        Methode.__init__(self, planning)
        self.degree_of_destruction = degree_of_destruction
        if weights is not None:
            self.weights = weights
        else:
            self.weights = [3, 2, 1, 0.5]
        self.operator_decay = operator_decay
        self.iterations = iterations
        self.collect_stats = collect_stats
        self.seed = seed
        if seed is not None:
            self.random_state = RandomState(seed)
        else:
            self.random_state = RandomState()
        self.alns = alns.ALNS(self.random_state)
        self.state = PlanningState(planning, degree_of_destruction)
        self.criterion = None
        self.destroy_operators = []
        self.repair_operators = []
        self.result = None

    def add_destroy_operators(self, *operators):
        # *operators is 'random' and/or 'worst'
        self.destroy_operators = [operator.lower() for operator in operators]
        if 'random' in self.destroy_operators:
            self.alns.add_destroy_operator(random_removal)
        if 'worst' in operators:
            self.alns.add_destroy_operator(worst_removal)

    def add_repair_operators(self, *operators):
        # *operators is 'random', 'greedy', 'reversed_random', and/or 'reversed_greedy'
        self.repair_operators = [operator.lower() for operator in operators]
        if 'random' in self.repair_operators:
            self.alns.add_repair_operator(random_repair)
        if 'greedy' in operators:
            self.alns.add_repair_operator(greedy_repair)
        if 'reversed_random' in operators:
            self.alns.add_repair_operator(reversed_random_repair)
        if 'reversed_greedy' in operators:
            self.alns.add_repair_operator(reversed_greedy_repair)

    def add_hill_climbing(self):
        self.criterion = alns.criteria.HillClimbing()

    def add_simulated_annealing(self, start_temperature: float = 10000, end_temperature: float = 1, step: float = 0.9,
                                method: str = "exponential"):
        # method is 'exponential' by default, can also be 'linear'
        # temperature = max(end_temperature, temperature - step) (if method is linear)
        # temperature = max(end_temperature, step * temperature) (if method is exponential)
        # where the initial temperature is set to start_temperature
        self.criterion = alns.criteria.SimulatedAnnealing(start_temperature, end_temperature, step, method)

    def solve(self):
        start = time()
        self.state = greedy_repair(self.state, self.random_state)
        initial_cost = self.state.objective() * 1000
        self.result = self.alns.iterate(self.state, self.weights, self.operator_decay, self.criterion, self.iterations,
                                        self.collect_stats)
        self.planning = self.result.best_state.planning
        print("Elapsed time:", round(time() - start, 2), 'sec')
        print("Initial cost:", initial_cost)
        print("Minimized cost:", self.result.best_state.objective() * 1000)

    def plot_objectives(self):
        self.result.plot_objectives()

    def plot_operators(self):
        figure = plt.figure("operator_counts", figsize=(14, 6))
        figure.subplots_adjust(bottom=0.15, hspace=.5)
        self.result.plot_operator_counts(figure=figure, title="Operator diagnostics",
                                         legend=["Best", "Better", "Accepted"])


