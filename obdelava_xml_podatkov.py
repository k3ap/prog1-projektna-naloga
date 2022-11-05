import xml.sax
from enum import Enum
from collections import defaultdict
import csv


class State(Enum):
    LEXICAL_ENTRY = 1
    WORD_FORM = 2
    FORM_REPRESENTATION = 3
    LEMMA = 4


class Handler(xml.sax.ContentHandler):
    def __init__(self):

        # Položaj v stroju (sklad)
        self.states = []

        # Seznam najdenih besed in njihovega najpogostejšega naglasa
        # zapis_oblike : (pogostost, naglasna_mesta_besede)
        self.besede = defaultdict(lambda: (0, ""))

        self.zadnji_zapis_oblike = None
        self.zadnja_pogostost = None
        self.zadnja_naglasna_mesta = None

    def startElement(self, tag, attrs):
        attrs = self._attrs_kot_dict(attrs)

        if tag == "LexicalEntry":
            self.states.append(State.LEXICAL_ENTRY)

        elif tag == "WordForm":
            self.states.append(State.WORD_FORM)

        elif tag == "FormRepresentation":
            self.states.append(State.FORM_REPRESENTATION)

        elif tag == "Lemma":
            self.states.append(State.LEMMA)

        elif tag == "feat":
            if not self.states:
                # na čistem začetku
                return

            if self.states[-1] == State.FORM_REPRESENTATION:
                if attrs["att"] == "zapis_oblike":
                    self.zadnji_zapis_oblike = attrs["val"]

                elif attrs["att"] == "pogostnost":
                    self.zadnja_pogostost = int(attrs["val"])

                elif attrs["att"] == "naglasna_mesta_besede":
                    self.zadnja_naglasna_mesta = attrs["val"]

    def endElement(self, tag):
        if tag in ("LexicalEntry", "WordForm", "FormRepresentation", "Lemma"):
            self.states.pop()

        if tag == "FormRepresentation":
            if self.besede[self.zadnji_zapis_oblike][0] <= self.zadnja_pogostost:
                self.besede[self.zadnji_zapis_oblike] =\
                    (self.zadnja_pogostost, self.zadnja_naglasna_mesta)

                self.zadnji_zapis_oblike = None
                self.zadnja_pogostost = None
                self.zadnja_naglasna_mesta = None

    def _attrs_kot_dict(self, attrs):
        d = {}
        for key in attrs.getNames():
            d[key] = attrs.getValue(key)
        return d


def obdelaj_besede(ime_vhodne_datoteke, ime_izhodne_datoteke):
    handler = Handler()
    xml.sax.parse(ime_vhodne_datoteke, handler)
    with open(ime_izhodne_datoteke, "w") as f:
        writer = csv.writer(f)
        for beseda in handler.besede.keys():
            writer.writerow((beseda, handler.besede[beseda][1]))
