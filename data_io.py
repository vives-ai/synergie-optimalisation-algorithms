from __future__ import annotations
from abc import ABC, abstractmethod
import json
import pandas as pd
import os
from datetime import datetime, time, timedelta
from .synchrotool import Planning, Order, AdhocLegs


class Object:

    def __init__(self, naam: str = ""):
        self.planning = Planning(naam=naam)


class DataObject(ABC, Object):

    def __init__(self, data, naam: str = ""):
        Object.__init__(self, naam)
        self.data = data
        self._locaties = {}
        self._containertypes = {}
        self._periode = []
        self._dagen = dict(zip(['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag'], range(7)))

    @abstractmethod
    def geef_planning_object(self):
        pass

    @abstractmethod
    def _voeg_locaties_toe(self):
        pass

    @abstractmethod
    def _voeg_containertypes_toe(self):
        pass

    @abstractmethod
    def _voeg_orders_toe(self):
        pass

    @abstractmethod
    def _voeg_legs_toe(self):
        pass

    def _check_periode(self, order: Order):
        if not self._periode:
            self._periode.append(order.min_ophaaltijd.date())
            self._periode.append(order.uiterste_levertijd.date())
        else:
            if order.min_ophaaltijd.date() < self._periode[0]:
                self._periode[0] = order.min_ophaaltijd.date()
            if order.uiterste_levertijd.date() > self._periode[1]:
                self._periode[1] = order.uiterste_levertijd.date()

    def _bepaal_tijden(self, dag: str, checkin: time, vertrek: time, duur: timedelta):
        aantal_dagen = timedelta(days=self._dagen[dag.lower()] - self._periode[0].weekday())
        checkin_date = self._periode[0] + aantal_dagen
        checkin_datetime = datetime.combine(checkin_date, checkin)
        if vertrek >= checkin:
            vertrek_datetime = datetime.combine(checkin_date, vertrek)
        else:
            vertrek_datetime = datetime.combine(checkin_date + timedelta(days=1), vertrek)
        aankomst_datetime = vertrek_datetime + duur
        return checkin_datetime, vertrek_datetime, aankomst_datetime


class JsonObject(DataObject):

    def __init__(self, data: dict, naam: str = ""):
        DataObject.__init__(self, data, naam)

    def geef_planning_object(self):
        self._voeg_locaties_toe()
        self._voeg_containertypes_toe()
        self._voeg_orders_toe()
        self._voeg_legs_toe()
        snelheid = self.data['adHocLegProperties']['snelheid']
        starttarief = self.data['adHocLegProperties']['starttarief']
        tarief = self.data['adHocLegProperties']['tarief']
        emissie = self.data['adHocLegProperties']['co2']
        voor_na_transport = self.data['adHocLegProperties']['voorEnNaTransport']
        afstanden = pd.DataFrame(self.data['adHocLegAfstanden'])
        self.planning.adhoc_legs = AdhocLegs(afstanden, starttarief, tarief, snelheid, emissie, voor_na_transport)
        return self.planning

    def _voeg_locaties_toe(self):
        locaties = set()
        for leg in self.data['legs']:
            leg['van'] = self.__check_locatie_str(leg['van'])
            locaties.add(leg['van'])
            leg['naar'] = self.__check_locatie_str(leg['naar'])
            locaties.add(leg['naar'])
        for order in self.data['orders']:
            order['van'] = self.__check_locatie_str(order['van'])
            locaties.add(order['van'])
            order['naar'] = self.__check_locatie_str(order['naar'])
            locaties.add(order['naar'])
        for locatie in locaties:
            naam, functie = tuple(locatie.split(" "))
            if functie == "Verlader":
                self._locaties[locatie] = self.planning.voeg_verlader_toe(naam)
            elif functie == "Terminal":
                self._locaties[locatie] = self.planning.voeg_terminal_toe(naam)
            elif functie == "Empty Depot":
                self._locaties[locatie] = self.planning.voeg_empty_depot_toe(naam)

    @staticmethod
    def __check_locatie_str(locatie: str):
        lst = locatie.title().split(" ")
        return lst[0] + " " + lst[-1]

    def _voeg_containertypes_toe(self):
        gewicht = self.data['adHocLegProperties']['containergewicht']
        containertypes = set()
        for leg in self.data['legs']:
            leg['containertype'] = leg['containertype'].strip().lower()
            containertypes.add(leg['containertype'])
        for order in self.data['orders']:
            order['containertype'] = order['containertype'].strip().lower()
            containertypes.add(order['containertype'])
        for containertype in containertypes:
            self._containertypes[containertype] = self.planning.voeg_containertype_toe(containertype, gewicht)

    def _voeg_orders_toe(self):
        for order_dict in self.data['orders']:
            min_ophaaltijd = datetime.strptime(order_dict['minOphaalTijd'], '%m-%d-%Y %H:%M:%S')
            max_ophaaltijd = datetime.strptime(order_dict['maxOphaalTijd'], '%m-%d-%Y %H:%M:%S')
            min_levertijd = datetime.strptime(order_dict['minLeverTijd'], '%m-%d-%Y %H:%M:%S')
            max_levertijd = datetime.strptime(order_dict['maxLeverTijd'], '%m-%d-%Y %H:%M:%S')
            uiterste_levertijd = datetime.strptime(order_dict['uitersteLeverTijd'], '%m-%d-%Y %H:%M:%S')
            order = self.planning.voeg_order_toe(self._locaties[order_dict['van']], self._locaties[order_dict['naar']],
                                                 min_ophaaltijd, max_ophaaltijd, min_levertijd, max_levertijd,
                                                 uiterste_levertijd, order_dict['emissieFactor'],
                                                 order_dict['boeteTeVroeg'], order_dict['boeteTeLaat'])
            if 'id' in order_dict:
                order.db_id = order_dict['id']
            self.planning.voeg_ordercapaciteit_toe(order, order_dict['aantal'],
                                                   self._containertypes[order_dict['containertype']])
            self._check_periode(order)

    def _voeg_legs_toe(self):
        for leg_dict in self.data['legs']:
            dag = leg_dict['dag'].strip()
            checkin = self.__datetime_str_to_time(leg_dict['checkin'])
            if leg_dict['vertrek'] is None:
                vertrek = checkin
            else:
                vertrek = self.__datetime_str_to_time(leg_dict['vertrek'])
            duur = timedelta(seconds=leg_dict['duur_uren'] * 3600.0 + leg_dict['duur_minuten'] * 60.0)
            checkin, vertrek, aankomst = self._bepaal_tijden(dag, checkin, vertrek, duur)
            leg = self.planning.voeg_leg_toe(self._locaties[leg_dict['van']], self._locaties[leg_dict['naar']],
                                             checkin, vertrek, aankomst)
            leg.dag = dag
            if 'id' in leg_dict:
                leg.db_id = leg_dict['id']
            self.planning.voeg_legcapaciteit_toe(leg, leg_dict['aantal'], self._containertypes[leg_dict['containertype']],
                                                 leg_dict['prijs'], leg_dict['co2'])

    @staticmethod
    def __datetime_str_to_time(dstr: str):
        d = datetime.strptime(dstr, '%m-%d-%Y %H:%M:%S')
        return time(d.hour, d.minute, d.second)


class DataFrameDict(DataObject):

    def __init__(self, data: dict, naam: str = ""):
        DataObject.__init__(self, data, naam)

    @property
    def legs(self):
        return self.data['legs']

    @property
    def legcapaciteiten(self):
        return self.data['legcapaciteiten']

    @property
    def orders(self):
        return self.data['orders']

    @property
    def ordercapaciteiten(self):
        return self.data['ordercapaciteiten']

    @property
    def adhoc_legs(self):
        return self.data['adhoc_legs']

    @property
    def afstanden(self):
        return self.data['afstanden']

    def geef_planning_object(self):
        self._voeg_locaties_toe()
        self._voeg_containertypes_toe()
        self._voeg_orders_toe()
        self._voeg_legs_toe()
        adhoc_legs = self.adhoc_legs.values.flatten()
        snelheid = adhoc_legs[0]
        starttarief = adhoc_legs[1]
        tarief = adhoc_legs[2]
        emissie = adhoc_legs[3]
        voor_na_transport = adhoc_legs[4]
        self.planning.adhoc_legs = AdhocLegs(self.afstanden, starttarief, tarief, snelheid, emissie, voor_na_transport)
        return self.planning

    def _voeg_locaties_toe(self):
        locaties = set(self.legs.van).union(set(self.legs.naar))
        for locatie in locaties:
            naam, functie = locatie.split(" ")
            functie = functie.upper()
            if functie == 'T':
                self._locaties[locatie] = self.planning.voeg_terminal_toe(naam)
            elif functie == 'V':
                self._locaties[locatie] = self.planning.voeg_verlader_toe(naam)
            elif functie == 'E':
                self._locaties[locatie] = self.planning.voeg_empty_depot_toe(naam)

    def _voeg_containertypes_toe(self):
        containertypes = set(self.legcapaciteiten.containertype).union(set(self.ordercapaciteiten.containertype))
        gewicht = self.adhoc_legs.values.flatten()[5]
        for containertype in containertypes:
            self._containertypes[containertype] = self.planning.voeg_containertype_toe(str(containertype) + 'ft', gewicht)

    def _voeg_orders_toe(self):
        for _, row in self.orders.iterrows():
            order = self.planning.voeg_order_toe(self._locaties[row.van], self._locaties[row.naar],
                                                 row.min_ophaaltijd.to_pydatetime(), row.max_ophaaltijd.to_pydatetime(),
                                                 row.min_levertijd.to_pydatetime(), row.max_levertijd.to_pydatetime(),
                                                 row.uiterste_levertijd.to_pydatetime(),
                                                 row.emissiefactor, row.boete_te_vroeg, row.boete_te_laat)
            for _, cap in self.ordercapaciteiten.iterrows():
                if cap.order == row.id:
                    self.planning.voeg_ordercapaciteit_toe(order, cap.aantal, self._containertypes[cap.containertype])
            self._check_periode(order)

    def _voeg_legs_toe(self):
        for _, row in self.legs.iterrows():
            duur = timedelta(seconds=row.duur.hour * 3600.0 + row.duur.minute * 60.0 + row.duur.second)
            checkin, vertrek, aankomst = self._bepaal_tijden(row.dag, row.checkin, row.vertrek, duur)
            leg = self.planning.voeg_leg_toe(self._locaties[row.van], self._locaties[row.naar], checkin, vertrek, aankomst)
            leg.dag = row.dag
            for _, cap in self.legcapaciteiten.iterrows():
                if cap.leg == row.id:
                    self.planning.voeg_legcapaciteit_toe(leg, int(cap.aantal), self._containertypes[cap.containertype],
                                                         cap.prijs, cap.emissie)


class DataFile(ABC, Object):

    def __init__(self, file: str):
        self.file = file
        _, naam = os.path.split(file)
        Object.__init__(self, naam)


class JsonFile(DataFile, JsonObject):

    def __init__(self, file: str):
        DataFile.__init__(self, file)
        with open(file) as f:
            data = json.load(f)
        JsonObject.__init__(self, data)


class ExcelFile(DataFile, DataFrameDict):

    def __init__(self, file: str):
        DataFile.__init__(self, file)
        data = dict()
        data['legs'] = pd.read_excel(self.file, sheet_name="legs")
        data['legcapaciteiten'] = pd.read_excel(self.file, sheet_name="legcapaciteiten")
        data['orders'] = pd.read_excel(self.file, sheet_name="orders")
        data['ordercapaciteiten'] = pd.read_excel(self.file, sheet_name="ordercapaciteiten")
        data['afstanden'] = pd.read_excel(self.file, sheet_name="afstanden", index_col=0)
        data['adhoc_legs'] = pd.read_excel(self.file, sheet_name="adhoc_legs", index_col=0, header=None)
        DataFrameDict.__init__(self, data)


class OptimizerResult:

    def __init__(self, planning: Planning):
        self.planning = planning

    def geef_legs(self, as_json=True):
        # retourneert OptimiserLegUse
        # als json object (as_json=True)
        # of als dict (as_json=False)
        leg_use = []
        for leg in self.planning.legs:
            for containertype, capaciteit in leg.capaciteiten.items():
                d = dict()
                d["legId"] = leg.id # moet leg.db_id worden
                d["containerType"] = str(containertype)
                d["used"] = len(capaciteit.containers)
                d["available"] = capaciteit.beschikbaar
                leg_use.append(d)
        return json.dumps(leg_use) if as_json else leg_use

    def geef_adhoc_legs(self, as_json=True):
        # retourneert AdhocLegs
        # als json object (as_json=True)
        # of als dict (as_json=False)
        caps = []
        for c in self.planning.adhoc_capaciteiten:
            leg_attr = ["id", "van", "naar", "vertrek", "aankomst"]
            cap_attr = ["aantal", "containertype", "prijs", "emissie"]
            d = dict()
            for attr in leg_attr:
                d[attr] = str(getattr(c.leg, attr))
            for attr in cap_attr:
                a = getattr(c, attr)
                d[attr] = str(a) if attr == "containertype" else a
            caps.append(d)
        return json.dumps(caps) if as_json else caps

    def geef_routes_per_order(self, as_json=True):
        # routes (= trajecten) gegroepeerd per order
        routes = []
        for order, trajecten in self.planning.geef_unieke_trajecten_per_order().items():
            for traject, attr in trajecten.items():
                d = dict()
                d["orderId"] = order.id  # moet order.db_id worden
                d["checkin"] = str(traject[0].leg.checkin)
                d["vertrek"] = str(traject[0].leg.vertrek)
                d["aankomst"] = str(traject[-1].leg.aankomst)
                d["amount"] = int(attr["aantal"])
                d["containerType"] = str(traject[0].containertype)
                d["prijs"] = attr["prijs"]
                d["co2"] = attr["emissie"]
                d["penalty"] = attr["boete"]
                d["LegsIds"] = [capaciteit.leg.id for capaciteit in traject]  # moet leg.db_id worden
                routes.append(d)
        return json.dumps(routes) if as_json else routes
