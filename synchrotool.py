from __future__ import annotations
import pandas as pd
from datetime import datetime, timedelta


class Object:

    def __init__(self, id: int):
        self.id = id
        self.db_id = ""

    def __repr__(self):
        return str(self.id)


class ObjectMetNaam(Object):

    def __init__(self, id: int, naam: str):
        Object.__init__(self, id)
        self.naam = naam

    def __repr__(self):
        return self.naam


class Locatie(ObjectMetNaam):

    def __init__(self, id: int, naam: str, functie: str):
        ObjectMetNaam.__init__(self, id, naam)
        self.functie = functie

    def is_terminal(self):
        return self.functie == 'Terminal'

    def is_verlader(self):
        return self.functie == 'Verlader'

    def is_empty_depot(self):
        return self.functie == 'Empty Depot'

    def __repr__(self):
        return f"{self.naam} {self.functie}"


class Terminal(Locatie):

    def __init__(self, id: int, naam: str):
        Locatie.__init__(self, id, naam, 'Terminal')


class Verlader(Locatie):

    def __init__(self, id: int, naam: str):
        Locatie.__init__(self, id, naam, 'Verlader')


class EmptyDepot(Locatie):

    def __init__(self, id: int, naam: str):
        Locatie.__init__(self, id, naam, 'Empty Depot')


class ContainerType(ObjectMetNaam):

    def __init__(self, id: int, naam: str, gewicht: float):
        # gewicht in Ton
        ObjectMetNaam.__init__(self, id, naam)
        self.gewicht = gewicht


class VanNaar(Object):

    def __init__(self, id: int, van: Locatie, naar: Locatie):
        Object.__init__(self, id)
        self.van = van
        self.naar = naar
        self.capaciteiten = {}

    @property
    def containers(self):
        return [container for capaciteit in self.capaciteiten.values() for container in capaciteit.containers]

    def _voeg_capaciteit_toe(self, containertype: ContainerType, capaciteit: Capaciteit):
        self.capaciteiten[containertype] = capaciteit

    def komt_voor(self, van_naar: VanNaar):
        # self.naar == van_naar.van?
        return self.naar == van_naar.van

    def komt_na(self, van_naar: VanNaar):
        # self.van == van_naar.naar?
        return self.van == van_naar.naar

    def zelfde_van(self, van_naar: VanNaar):
        # self.van == van_naar.van?
        return self.van == van_naar.van

    def zelfde_naar(self, van_naar: VanNaar):
        # self.naar == van_naar.naar?
        return self.naar == van_naar.naar

    def dataframe(self):
        return pd.DataFrame(dict(id=[self.id], van=[self.van], naar=[self.naar]))

    def __lt__(self, other):
        return self.komt_voor(other)

    def __gt__(self, other):
        return self.komt_na(other)

    def __repr__(self):
        return f"{self.id}: {self.van} - {self.naar}"


class Leg(VanNaar):

    def __init__(self, id: int, van: Locatie, naar: Locatie, checkin: datetime, vertrek: datetime, aankomst: datetime):
        VanNaar.__init__(self, id, van, naar)
        self.checkin = checkin
        self.vertrek = vertrek
        self.aankomst = aankomst
        self.dag = ""
        self.modus = ""

    @property
    def duur(self):
        return self.aankomst - self.vertrek

    def voeg_capaciteit_toe(self, aantal: int, containertype: ContainerType, prijs: float, emissie: float):
        legcapaciteit = LegCapaciteit(self, aantal, containertype, prijs, emissie)
        self._voeg_capaciteit_toe(containertype, legcapaciteit)
        return legcapaciteit

    def aantal(self, containertype: ContainerType):
        return self.capaciteiten[containertype].aantal if containertype in self.capaciteiten else 0

    def beschikbaar(self, containertype: ContainerType):
        return self.capaciteiten[containertype].beschikbaar if containertype in self.capaciteiten else 0

    def prijs(self, containertype: ContainerType):
        return self.capaciteiten[containertype].prijs if containertype in self.capaciteiten else 0

    def emissie(self, containertype: ContainerType):
        return self.capaciteiten[containertype].emissie if containertype in self.capaciteiten else 0

    def komt_voor(self, leg: Leg):
        return VanNaar.komt_voor(self, leg) and self.aankomst <= leg.checkin

    def komt_na(self, leg: Leg):
        return VanNaar.komt_na(self, leg) and self.checkin >= leg.aankomst

    def is_mogelijk_begin(self, order: Order):
        return self.zelfde_van(order) and \
               order.min_ophaaltijd <= self.checkin <= order.max_ophaaltijd

    def is_mogelijk_einde(self, order: Order):
        return self.zelfde_naar(order) and \
               self.aankomst <= order.uiterste_levertijd

    def dataframe(self):
        df1 = VanNaar.dataframe(self)
        df1.columns = ["leg_" + column for column in df1.columns]
        df2 = pd.DataFrame(dict(dag=[self.dag], checkin=[self.checkin], vertrek=[self.vertrek], aankomst=[self.aankomst]))
        return pd.concat((df1, df2), axis=1)

    def __repr__(self):
        if self.modus == "":
            return f"{self.id}: {self.van} - {self.naar}"
        else:
            return f"{self.id}: {self.van} - {self.naar} ({self.modus})"


class Order(VanNaar):

    def __init__(self, id: int, van: Locatie, naar: Locatie,
                 min_ophaaltijd: datetime, max_ophaaltijd: datetime,
                 min_levertijd: datetime, max_levertijd: datetime, uiterste_levertijd: datetime,
                 emissiefactor: float, boete_te_vroeg: float, boete_te_laat: float):
        VanNaar.__init__(self, id, van, naar)
        self.min_ophaaltijd = min_ophaaltijd
        self.max_ophaaltijd = max_ophaaltijd
        self.min_levertijd = min_levertijd
        self.max_levertijd = max_levertijd
        self.uiterste_levertijd = uiterste_levertijd
        self.emissiefactor = emissiefactor
        self.boete_te_vroeg = boete_te_vroeg
        self.boete_te_laat = boete_te_laat

    def voeg_capaciteit_toe(self, aantal: int, containertype: ContainerType):
        ordercapaciteit = OrderCapaciteit(self, aantal, containertype)
        self._voeg_capaciteit_toe(containertype, ordercapaciteit)
        return ordercapaciteit

    def dataframe(self):
        df1 = VanNaar.dataframe(self)
        df1.columns = ["order_" + column for column in df1.columns]
        df2 = pd.DataFrame(dict(min_ophaaltijd=[self.min_ophaaltijd], max_ophaaltijd=[self.max_ophaaltijd],
                                min_levertijd=[self.min_levertijd], max_levertijd=[self.max_levertijd],
                                uiterste_levertijd=[self.uiterste_levertijd], emissiefactor=[self.emissiefactor],
                                boete_te_vroeg=[self.boete_te_vroeg], boete_te_laat=[self.boete_te_laat]))
        return pd.concat((df1, df2), axis=1)


class Capaciteit:

    def __init__(self, van_naar: VanNaar, aantal: int, containertype: ContainerType):
        self._van_naar = van_naar
        self.aantal = aantal
        self.containertype = containertype
        self.containers = []

    def __repr__(self):
        return f"{self._van_naar} ({self.aantal} {self.containertype})"

    def dataframe(self):
        df = pd.DataFrame(dict(aantal=[self.aantal], containertype=[self.containertype]))
        return pd.concat((self._van_naar.dataframe(), df), axis=1)


class LegCapaciteit(Capaciteit):

    def __init__(self, leg: Leg, aantal: int, containertype: ContainerType,
                 prijs: float, emissie: float):
        Capaciteit.__init__(self, leg, aantal, containertype)
        self.prijs = prijs
        self.emissie = emissie

    @property
    def leg(self):
        return self._van_naar

    @property
    def beschikbaar(self):
        return self.aantal - len(self.containers)

    def komt_voor(self, legcapaciteit: LegCapaciteit):
        return self.leg.komt_voor(legcapaciteit.leg) and \
               self.containertype == legcapaciteit.containertype and \
               self.beschikbaar > 0

    def komt_na(self, legcapaciteit: LegCapaciteit):
        return self.leg.komt_na(legcapaciteit.leg) and \
               self.containertype == legcapaciteit.containertype and \
               self.beschikbaar > 0

    def is_mogelijk_begin(self, container: Container):
        return self.leg.is_mogelijk_begin(container.order) and \
               self.containertype == container.containertype and \
               self.beschikbaar > 0

    def is_mogelijk_einde(self, container: Container):
        return self.leg.is_mogelijk_einde(container.order) and \
               self.containertype == container.containertype and \
               self.beschikbaar > 0

    def dataframe(self):
        df1 = Capaciteit.dataframe(self).rename(columns=dict(aantal="leg_aantal", containertype="leg_containertype"))
        df2 = pd.DataFrame(dict(prijs=[self.prijs], emissie=[self.emissie]))
        return pd.concat((df1, df2), axis=1)

    def __lt__(self, other):
        return self.leg < other.leg

    def __gt__(self, other):
        return self.leg > other.leg


class OrderCapaciteit(Capaciteit):

    def __init__(self, order: Order, aantal: int, containertype: ContainerType):
        Capaciteit.__init__(self, order, aantal, containertype)

    @property
    def order(self):
        return self._van_naar

    def dataframe(self):
        return Capaciteit.dataframe(self).rename(columns=dict(aantal="order_aantal", containertype="order_containertype"))


class Container(Object):

    def __init__(self, id: int, ordercapaciteit: OrderCapaciteit):
        Object.__init__(self, id)
        self.ordercapaciteit = ordercapaciteit

    @property
    def containertype(self):
        return self.ordercapaciteit.containertype

    @property
    def order(self):
        return self.ordercapaciteit.order

    @property
    def van(self):
        return self.order.van

    @property
    def naar(self):
        return self.order.naar

    @property
    def min_ophaaltijd(self):
        return self.order.min_ophaaltijd

    @property
    def max_ophaaltijd(self):
        return self.order.max_ophaaltijd

    @property
    def min_levertijd(self):
        return self.order.min_levertijd

    @property
    def max_levertijd(self):
        return self.order.max_levertijd

    @property
    def uiterste_levertijd(self):
        return self.order.uiterste_levertijd

    @property
    def emissiefactor(self):
        return self.order.emissiefactor

    @property
    def boete_te_vroeg(self):
        return self.order.boete_te_vroeg

    @property
    def boete_te_laat(self):
        return self.order.boete_te_laat

    def dataframe(self):
        return pd.concat((pd.DataFrame(dict(containerid=[self.id])), self.ordercapaciteit.dataframe()), axis=1)

    def __repr__(self):
        return f"{self.containertype}: {self.order}"


class Planning:

    def __init__(self, adhoc_legs: AdhocLegs = None, naam: str = 'SynchroTool'):
        self.naam = naam
        self.adhoc_legs = adhoc_legs
        self.locaties = []
        self.terminals = []
        self.verladers = []
        self.empty_depots = []
        self.containertypes = []
        self.legs = []
        self.legcapaciteiten = []
        self.adhoc_capaciteiten = []
        self.orders = []
        self.ordercapaciteiten = []
        self.containers = []  # list: containers[i] -> OrderCapaciteit object van container i
        self.trajecten = []  # list: trajecten[i] -> traject van container i = list van opeenvolgende legcapaciteiten
        self.kosten = []  # list: kosten[i] -> kost van traject i
        self.te_plannen = set()  # set met ids van containers die nog in te plannen zijn
        self.gepland = set()  # set met ids van containers die al ingepland zijn

    def __voeg_locatie_toe(self, naam: str, functie):
        # functie is klasse: Terminal, Verlader of EmptyDepot
        id = len(self.locaties)
        locatie = functie(id, naam)
        self.locaties.append(locatie)
        return locatie

    def voeg_terminal_toe(self, naam: str):
        terminal = self.__voeg_locatie_toe(naam, Terminal)
        self.terminals.append(terminal)
        return terminal

    def voeg_verlader_toe(self, naam: str):
        verlader = self.__voeg_locatie_toe(naam, Verlader)
        self.verladers.append(verlader)
        return verlader

    def voeg_empty_depot_toe(self, naam: str):
        empty_depot = self.__voeg_locatie_toe(naam, EmptyDepot)
        self.empty_depots.append(empty_depot)
        return empty_depot

    def voeg_containertype_toe(self, naam: str, gewicht: float):
        id = len(self.containertypes)
        containertype = ContainerType(id, naam, gewicht)
        self.containertypes.append(containertype)
        return containertype

    def voeg_leg_toe(self, van: Locatie, naar: Locatie, checkin: datetime, vertrek: datetime, aankomst: datetime):
        id = len(self.legs)
        leg = Leg(id, van, naar, checkin, vertrek, aankomst)
        self.legs.append(leg)
        return leg

    def voeg_legcapaciteit_toe(self, leg: Leg, aantal: int, containertype: ContainerType, prijs: float, emissie: float):
        legcapaciteit = leg.voeg_capaciteit_toe(aantal, containertype, prijs, emissie)
        self.legcapaciteiten.append(legcapaciteit)
        return legcapaciteit

    def voeg_order_toe(self, van: Locatie, naar: Locatie,
                       min_ophaaltijd: datetime, max_ophaaltijd: datetime,
                       min_levertijd: datetime, max_levertijd: datetime, uiterste_levertijd: datetime,
                       emissiefactor: float, boete_te_vroeg: float, boete_te_laat: float):
        id = len(self.orders)
        order = Order(id, van, naar, min_ophaaltijd, max_ophaaltijd,
                      min_levertijd, max_levertijd, uiterste_levertijd,
                      emissiefactor, boete_te_vroeg, boete_te_laat)
        self.orders.append(order)
        return order

    def voeg_ordercapaciteit_toe(self, order: Order, aantal: int, containertype: ContainerType):
        ids = [len(self.containers) + id for id in range(aantal)]  # nieuwe container ids
        ordercapaciteit = order.voeg_capaciteit_toe(aantal, containertype)
        ordercapaciteit.containers = ids
        self.ordercapaciteiten.append(ordercapaciteit)
        self.containers += [ordercapaciteit] * aantal
        self.te_plannen = self.te_plannen.union(ids)
        self.trajecten += [[] for _ in range(aantal)]
        self.kosten += [None for _ in range(aantal)]
        return ordercapaciteit

    def geef_container_object(self, container_id: int):
        return Container(container_id, self.containers[container_id])

    def geef_containers(self):
        for container_id in range(len(self.containers)):
            yield self.geef_container_object(container_id)

    def geef_container_traject(self, container_id: int):
        return self.trajecten[container_id]

    def voeg_container_traject_toe(self, container_id: int, *traject):
        for legcapaciteit in traject:
            legcapaciteit.containers.append(container_id)
            if legcapaciteit not in self.legcapaciteiten:
                self.adhoc_capaciteiten.append(legcapaciteit)
        self.trajecten[container_id] = self.__sorteer_container_traject(container_id, *traject)
        self.kosten[container_id] = self.geef_totale_kost_van_container_traject(container_id)
        self.te_plannen.remove(container_id)
        self.gepland.add(container_id)

    def __sorteer_container_traject(self, container_id: int, *traject):
        if all([traject[i] < traject[i + 1] for i in range(len(traject) - 1)]):
            return traject
        else:
            traject = list(traject)
            sorted_capaciteiten = []
            van = self.geef_container_object(container_id).order.van
            while traject:
                for legcapaciteit in traject:
                    if van == legcapaciteit.leg.van:
                        van = legcapaciteit.leg.naar
                        traject.remove(legcapaciteit)
                        sorted_capaciteiten.append(legcapaciteit)
                        break
            return tuple(sorted_capaciteiten)

    def verwijder_container_traject(self, container_id: int):
        for legcapaciteit in self.trajecten[container_id]:
            legcapaciteit.containers.remove(container_id)
            if legcapaciteit in self.adhoc_capaciteiten:
                self.adhoc_capaciteiten.remove(legcapaciteit)
        self.trajecten[container_id] = []
        self.kosten[container_id] = None
        self.gepland.remove(container_id)
        self.te_plannen.add(container_id)

    def verwijder_alle_trajecten(self):
        for i in range(len(self.containers)):
            self.verwijder_container_traject(i)

    def geef_prijs_van_container_traject(self, container_id: int):
        # prijs van 1 gegeven containertraject
        traject = self.trajecten[container_id]
        if traject:
            return sum([legcapaciteit.prijs for legcapaciteit in traject])
        return None

    def geef_emissie_van_container_traject(self, container_id: int):
        # emissie van 1 gegeven containertraject
        container = self.geef_container_object(container_id)
        traject = self.trajecten[container_id]
        if traject:
            emissie = sum([legcapaciteit.emissie for legcapaciteit in traject])
            return dict(emissie=emissie, kost=emissie * container.emissiefactor)
        return None

    def geef_boete_van_container_traject(self, container_id: int):
        # boete van 1 gegeven containertraject
        container = self.geef_container_object(container_id)
        traject = self.trajecten[container_id]
        if traject:
            aankomst = traject[-1].leg.aankomst
            if aankomst > container.max_levertijd:
                uren_te_laat = (aankomst - container.max_levertijd).total_seconds() / 3600.0
                return dict(uren_te_vroeg=0, uren_te_laat=uren_te_laat, boete=uren_te_laat * container.boete_te_laat)
            elif aankomst < container.min_levertijd:
                uren_te_vroeg = (container.min_levertijd - aankomst).total_seconds() / 3600.0
                return dict(uren_te_vroeg=uren_te_vroeg, uren_te_laat=0, boete=uren_te_vroeg * container.boete_te_vroeg)
            else:
                return dict(uren_te_vroeg=0, uren_te_laat=0, boete=0.0)
        return None

    def geef_totale_kost_van_container_traject(self, container_id: int):
        # totale kost van 1 gegeven containertraject
        prijs = self.geef_prijs_van_container_traject(container_id)
        emissie = self.geef_emissie_van_container_traject(container_id)["kost"]
        boete = self.geef_boete_van_container_traject(container_id)["boete"]
        try:
            return prijs + emissie + boete
        except:
            return None

    def geef_totale_kost(self):
        # totale kostprijs van de planning (incl emissie en boetes)
        return sum([kost for kost in self.kosten if kost is not None])

    def maak_unieke_adhoc_capaciteiten(self):
        # zorgt dat unieke adhoc capaciteiten worden samengevoegd
        new_adhoc_capaciteiten = []
        id = 0  # adhoc ids
        for c_old in self.adhoc_capaciteiten:
            exists = False
            for c_new in new_adhoc_capaciteiten:
                exists = self.__zelfde_adhoc_capaciteit(c_old, c_new)
                if exists:
                    container = c_old.containers[0]
                    c_new.containers.append(container)
                    c_new.aantal += 1
                    for i, c in enumerate(self.trajecten[container]):
                        if c == c_old:
                            lst = list(self.trajecten[container])
                            lst[i] = c_new
                            self.trajecten[container] = tuple(lst)
                    break
            if not exists:
                id -= 1
                c_old.leg.id = id
                new_adhoc_capaciteiten.append(c_old)
        self.adhoc_capaciteiten = new_adhoc_capaciteiten

    @staticmethod
    def __zelfde_adhoc_capaciteit(cap1: LegCapaciteit, cap2: LegCapaciteit):
        leg_attributes = ["van", "naar", "checkin", "vertrek", "aankomst"]
        legcap_attributes = ["containertype", "prijs", "emissie"]
        for attr in leg_attributes:
            if getattr(cap1.leg, attr) != getattr(cap2.leg, attr):
                return False
        for attr in legcap_attributes:
            if getattr(cap1, attr) != getattr(cap2, attr):
                return False
        return True

    def geef_unieke_trajecten(self, groepeer_orders=False):
        # groepeert trajecten
        # geeft unieke trajecten als [{traject: [container_ids]}] als groepeer_orders=False (default)
        # en als [{traject: {order: aantal}}] als groepeer_orders=True
        trajecten = dict()
        for container_id, traject in enumerate(self.trajecten):
            if traject not in trajecten:
                if groepeer_orders:
                    trajecten[traject] = dict()
                else:
                    trajecten[traject] = []
            if groepeer_orders:
                order = self.geef_container_object(container_id).order
                if order not in trajecten[traject]:
                    trajecten[traject][order] = 0
                trajecten[traject][order] += 1
            else:
                trajecten[traject].append(container_id)
        return trajecten

    def geef_unieke_trajecten_per_order(self):
        # groepeert trajecten per order
        # retourneert [{order: traject: aantal_containers}]
        order_trajecten = dict()
        for order in self.orders:
            order_trajecten[order] = dict()
            for container_id in order.containers:
                traject = self.trajecten[container_id]
                if traject not in order_trajecten[order]:
                    order_trajecten[order][traject] = dict(aantal=0, prijs=0, emissie=0, boete=0)
                order_trajecten[order][traject]["aantal"] += 1
                order_trajecten[order][traject]["prijs"] += self.geef_prijs_van_container_traject(container_id)
                order_trajecten[order][traject]["emissie"] += self.geef_emissie_van_container_traject(container_id)["emissie"]
                order_trajecten[order][traject]["boete"] += self.geef_boete_van_container_traject(container_id)["boete"]
        return order_trajecten

    def dataframe(self, attribuut: str = 'orders'):
        # attribuut is 'orders' (default), 'legs', 'ordercapaciteiten', 'legcapaciteiten', 'containers', 'trajecten'
        if attribuut == 'containers':
            return pd.concat([self.geef_container_object(id).dataframe() for id in range(len(self.containers))],
                             axis=0, ignore_index=True)
        elif attribuut == 'trajecten':
            return pd.concat([pd.concat((self.geef_container_object(id).dataframe(),
                                         pd.DataFrame(dict(leg_volgorde=[nr])),
                                         lc.dataframe()),
                                        axis=1)
                              for id, traject in enumerate(self.trajecten) for nr, lc in enumerate(traject)],
                             axis=0, ignore_index=True)
        else:
            return pd.concat([member.dataframe() for member in getattr(self, attribuut)], axis=0, ignore_index=True)


class AdhocLegs:

    def __init__(self, afstanden: pd.DataFrame, starttarief: float, tarief: float, snelheid: float, emissie: float,
                 voor_na_transport: float = 10.0):
        # afstanden is afstandsmatrix met afstanden in km
        # starttarief in euro
        # tarief in euro/km
        # snelheid in km/u
        # emissie in kg/ton/km
        # voor_na_transport in km
        self.afstanden = afstanden
        self.starttarief = starttarief
        self.tarief = tarief
        self.snelheid = snelheid
        self.emissie = emissie
        self.voor_na_transport = voor_na_transport

    def geef_afstand(self, van: Locatie, naar: Locatie):
        afstand = self.afstanden[van.naam][naar.naam]
        if int(afstand) == 0 and van.naam != naar.naam:
            afstand = self.voor_na_transport
        return afstand

    def maak_leg(self, container: Container):
        # maakt adhoc leg tussen start- en eindlocatie van een container
        # retourneert LegCapaciteit object!
        afstand = self.geef_afstand(container.van, container.naar)
        duur = timedelta(seconds=afstand / self.snelheid * 3600.0)
        max_duur = container.uiterste_levertijd - container.min_ophaaltijd
        min_duur = container.min_levertijd - container.max_ophaaltijd
        max_duur_geen_boete = container.max_levertijd - container.min_ophaaltijd
        if duur > max_duur:  # niet mogelijk
            return None
        elif duur <= min_duur:  # te vroeg
            vertrek = container.max_ophaaltijd
        elif duur >= max_duur_geen_boete:  # te laat
            vertrek = container.min_ophaaltijd
        else:
            ophaalvenster = container.max_ophaaltijd - container.min_ophaaltijd
            delta = duur - min_duur
            if delta >= ophaalvenster:
                vertrek = container.min_ophaaltijd
            else:
                vertrek = container.min_levertijd - duur
        leg = Leg(-999, container.van, container.naar, vertrek, vertrek, vertrek + duur)
        prijs = self.starttarief + afstand * self.tarief
        emissie = self.emissie * afstand * container.containertype.gewicht
        legcapaciteit = leg.voeg_capaciteit_toe(1, container.containertype, prijs, emissie)
        return legcapaciteit

    def maak_leg_voor_leg(self, leg_erna: Leg, container: Container):
        # maakt adhoc leg voor een gegeven leg
        # de adhoc leg start in container.van
        # retourneert LegCapaciteit object!
        afstand = self.geef_afstand(leg_erna.van, container.van)
        duur = timedelta(seconds=afstand / self.snelheid * 3600.0)
        if duur > (leg_erna.checkin - container.min_ophaaltijd):
            return None
        else:
            vertrek = container.min_ophaaltijd
            leg = Leg(-999, container.van, leg_erna.van, vertrek, vertrek, vertrek + duur)
            prijs = self.starttarief + afstand * self.tarief
            emissie = self.emissie * afstand * container.containertype.gewicht
            legcapaciteit = leg.voeg_capaciteit_toe(1, container.containertype, prijs, emissie)
            return legcapaciteit

    def maak_leg_na_leg(self, leg_ervoor: Leg, container: Container):
        # maakt adhoc leg na een gegeven leg
        # de adhoc leg eindigt in container.naar
        # retourneert LegCapaciteit object!
        aankomst = leg_ervoor.aankomst
        afstand = self.geef_afstand(leg_ervoor.naar, container.naar)
        duur = timedelta(seconds=afstand / self.snelheid * 3600.0)
        if duur > (container.uiterste_levertijd - aankomst):
            return None
        elif duur < (container.min_levertijd - aankomst):
            vertrek = container.min_levertijd - duur
        else:
            vertrek = aankomst
        leg = Leg(-999, leg_ervoor.naar, container.naar, vertrek, vertrek, vertrek + duur)
        prijs = self.starttarief + afstand * self.tarief
        emissie = self.emissie * afstand * container.containertype.gewicht
        legcapaciteit = leg.voeg_capaciteit_toe(1, container.containertype, prijs, emissie)
        return legcapaciteit

    def schat_prijs(self, legcapaciteit: LegCapaciteit, container: Container, van_naar: bool = True):
        # schat prijs vanaf of naar gegeven legcapaciteit
        # van_naar = True: traject wordt geconstrueerd van container.van naar container.naar
        # van_naar = False: traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        if van_naar:
            afstand = self.geef_afstand(legcapaciteit.leg.naar, container.naar)
        else:
            afstand = self.geef_afstand(container.van, legcapaciteit.leg.van)
        if afstand > 0:
            return legcapaciteit.prijs + self.starttarief + afstand * self.tarief
        else:
            return legcapaciteit.prijs

    def schat_emissie(self, legcapaciteit: LegCapaciteit, container: Container, van_naar: bool = True):
        # schat emissie vanaf of naar gegeven legcapaciteit
        # van_naar = True: traject wordt geconstrueerd van container.van naar container.naar
        # van_naar = False: traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        if van_naar:
            afstand = self.geef_afstand(legcapaciteit.leg.naar, container.naar)
        else:
            afstand = self.geef_afstand(container.van, legcapaciteit.leg.van)
        if afstand > 0:
            return legcapaciteit.emissie + self.emissie * afstand * legcapaciteit.containertype.gewicht
        else:
            return legcapaciteit.emissie

    def schat_aankomst(self, legcapaciteit: LegCapaciteit, container: Container):
        # schat aankomst in container.naar vanaf gegeven legcapaciteit
        leg = legcapaciteit.leg
        afstand = self.geef_afstand(leg.naar, container.naar)
        if afstand > 0:
            return leg.aankomst + timedelta(seconds=afstand / self.snelheid * 3600.0)
        else:
            return leg.aankomst

    def schat_vertrek(self, legcapaciteit: LegCapaciteit, container: Container):
        # schat vertrek in container.van naar gegeven legcapaciteit
        leg = legcapaciteit.leg
        afstand = self.geef_afstand(container.van, leg.van)
        if afstand > 0:
            return leg.checkin - timedelta(seconds=afstand / self.snelheid * 3600.0)
        else:
            return leg.checkin

    def schat_totale_kost(self, legcapaciteit: LegCapaciteit, container: Container, van_naar: bool = True):
        # schat totale kost vanaf of naar gegeven legcapaciteit
        # van_naar = True: traject wordt geconstrueerd van container.van naar container.naar
        # van_naar = False: traject wordt omgekeerd geconstrueerd van container.naar naar container.van
        prijs = self.schat_prijs(legcapaciteit, container, van_naar)
        emissie = self.schat_emissie(legcapaciteit, container, van_naar)
        if van_naar:
            aankomst = self.schat_aankomst(legcapaciteit, container)
            if aankomst > container.uiterste_levertijd:
                return None
            elif aankomst > container.max_levertijd:
                uren_te_laat = (aankomst - container.max_levertijd).total_seconds() / 3600.0
                return prijs + container.emissiefactor * emissie + container.boete_te_laat * uren_te_laat
            elif aankomst < container.min_levertijd:
                uren_te_vroeg = (container.min_levertijd - aankomst).total_seconds() / 3600.0
                return prijs + container.emissiefactor * emissie + container.boete_te_vroeg * uren_te_vroeg
            else:
                return prijs + container.emissiefactor * emissie
        else:
            vertrek = self.schat_vertrek(legcapaciteit, container)
            if vertrek < container.min_ophaaltijd:
                return None
            else:
                return prijs + container.emissiefactor * emissie
