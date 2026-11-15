"""Build src/scripts/data/region-pl.db: the Poland pack. What a medicine sold in Poland is, and a handful of
facts about getting care there, each with the law or the page it was read in.

  python tools/build_region_pl.py --fetch      download the register, the acts and the pages into downloads/, then build
  python tools/build_region_pl.py              build from what is already in downloads/
  python tools/build_region_pl.py --retrieved 2026-11-15     for files fetched by hand

Three kinds of thing are in the file, and each stays under its own terms:

  The register of medicines   Rejestr Produktow Leczniczych, kept by Centrum e-Zdrowia. The whole register as
                              one CSV file, the state at the end of the day before. On the government's open
                              data portal (https://dane.gov.pl, data set 397) it is CC BY 4.0, with the duty to
                              say when the data was made and when it was fetched; the build reads that entry
                              again at every fetch and stops if it says anything else. Only medicines for
                              people are kept, and of each: its name, the substance as the register names it
                              (in Latin), strength, form, route, ATC code, who holds the permit, and whether a
                              pack is sold with or without a prescription.

  Polish law                  quoted word for word, with the article. Legal acts are not under copyright in
                              Poland (art. 4 of the act on copyright, read on 15 November 2026). Acts come
                              from the Sejm's own service (https://api.sejm.gov.pl/eli). Where it gives an act
                              as HTML, the build looks the quoted words up again in the act and stops if they
                              are gone. Where it gives only a PDF, which the standard library cannot read, the
                              words were read by hand; the fact then says so, with the day.

  Official pages              NFZ, the Patient Ombudsman and the Ministry of Health. NFZ's pages are plain
                              copyright and gov.pl's texts are CC BY-SA 4.0, so NOT ONE SENTENCE is taken from
                              them: only single facts (a telephone number, opening hours), put in this
                              skill's own words, with the page named. At every fetch the build checks that the
                              page still states them.

What is not in it, on purpose: waiting times for treatment. Clinics report them to NFZ every week, so a copy
would be wrong within days; the pack says where NFZ publishes them live.

The facts are few, and they are written out below, in FACTS, where anyone can read and correct them. Each one
says what it rests on. A fact is this skill's wording; the quotation under it is the law's.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
from html import unescape

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, desk

STEM = "region-pl"
COUNTRY = "PL"
REGISTER_URL = "https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/public-pl-report/get-csv"
REGISTER_FILE = "rpl.csv"
REGISTER_PAGE = "https://rejestry.ezdrowie.gov.pl/rpl/search/public"
LICENCE_URL = "https://api.dane.gov.pl/1.4/datasets/397"
LICENCE_FILE = "rpl-licence.json"
LICENCE_NAME = "CC BY 4.0"
LEAFLET = "https://rejestrymedyczne.ezdrowie.gov.pl/api/rpl/medicinal-products/%d/leaflet"
LEAFLET_IMPORT = "https://rejestrymedyczne.ezdrowie.gov.pl/api/rpl/medicinal-products/%d/parallel-import-files/LEAFLET/public"
ELI = "https://api.sejm.gov.pl/eli/acts/"
# the register's name keeps its Polish letter: a credit line spells its source the way the source does
REGISTER_NAME = "Rejestr Produkt\u00f3w Leczniczych"
CREDIT = "Source: %s, Centrum e-Zdrowia (https://rejestry.ezdrowie.gov.pl)" % REGISTER_NAME
MIN_PRODUCTS = 15000
HUMAN = "Ludzki"
# the register's own stand-ins for a substance name, where there is no single one
NO_ONE_NAME = ("Produkt z\u0142o\u017cony", "Homeopatyczny produkt leczniczy")
# the columns that are read, by the names the register gives them
COLUMNS = {
    "id": "Identyfikator Produktu Leczniczego", "name": "Nazwa Produktu Leczniczego", "common": "Nazwa powszechnie stosowana",
    "kind": "Rodzaj preparatu", "route": "Droga podania - Gatunek - Tkanka - Okres karencji", "strength": "Moc",
    "form": "Posta\u0107 farmaceutyczna", "atc": "Kod ATC", "holder": "Podmiot odpowiedzialny", "packs": "Opakowanie",
    "parts": "Substancja czynna", "leaflet": "Ulotka", "leaflet_import": "Ulotka importu r\u00f3wnoleg\u0142ego",
    "exported_from": "Kraj eksportu",
}
READ = "2026-11-15"             # the day a person last read the sources that only a person can read


def law(name, place, eli, units=(), absent=(), base=None):
    """An act the Sejm's service gives as HTML. units: (the id of a unit in that HTML, words it must hold); the
    words are the quotation. absent: (unit, words it must NOT hold). base: the act a consolidated text is of."""
    return {"kind": "law", "name": name, "place": place, "eli": eli, "base": base, "units": tuple(units), "absent": tuple(absent)}


def law_by_hand(name, place, eli, quote):
    """An act that comes as a PDF only: read by a person, on READ."""
    return {"kind": "law", "name": name, "place": place, "eli": eli, "quote": quote, "by_hand": True}


def page(label, name, url, must):
    """An official page: nothing is copied from it, and it must still state these words."""
    return {"kind": "page", "label": label, "name": name, "place": "", "url": url, "must": tuple(must)}


NUMBER_PLAN = ("Rozporz\u0105dzenie Ministra Cyfryzacji z dnia 4 grudnia 2024 r. w sprawie planu numeracji krajowej dla publicznych "
               "sieci telekomunikacyjnych (Dz.U. 2024 poz. 1862)")
VEHICLES = ("Rozporz\u0105dzenie Ministra Infrastruktury z dnia 31 grudnia 2002 r. w sprawie warunk\u00f3w technicznych pojazd\u00f3w oraz "
            "zakresu ich niezb\u0119dnego wyposa\u017cenia (tekst jednolity: Dz.U. 2024 poz. 502)")
RIGHTS = ("Ustawa z dnia 6 listopada 2008 r. o prawach pacjenta i Rzeczniku Praw Pacjenta (tekst jednolity: Dz.U. 2024 poz. 581)")
CARE = ("Ustawa z dnia 27 sierpnia 2004 r. o \u015bwiadczeniach opieki zdrowotnej finansowanych ze \u015brodk\u00f3w publicznych "
        "(tekst jednolity: Dz.U. 2025 poz. 1461)")
WASTE = ("Ustawa z dnia 13 wrze\u015bnia 1996 r. o utrzymaniu czysto\u015bci i porz\u0105dku w gminach (tekst jednolity: Dz.U. 2025 poz. 733)")
RECORDS = ("Rozporz\u0105dzenie Ministra Zdrowia z dnia 6 kwietnia 2020 r. w sprawie rodzaj\u00f3w, zakresu i wzor\u00f3w dokumentacji medycznej "
           "oraz sposobu jej przetwarzania (tekst jednolity: Dz.U. 2026 poz. 1391)")
PHARMA = "Ustawa z dnia 6 wrze\u015bnia 2001 r. - Prawo farmaceutyczne (tekst jednolity: Dz.U. 2026 poz. 612)"
NFZ_SUDDEN = page("nfz-sudden", "NFZ, \"Nag\u0142a choroba? Gdzie si\u0119 leczy\u0107 w czasie \u015awi\u0105t Bo\u017cego Narodzenia? NFZ podpowiada\", "
                  "dated 23 December 2025",
                  "https://www.nfz.gov.pl/aktualnosci/aktualnosci-centrali/nagla-choroba-gdzie-sie-leczyc-w-czasie-swiat-bozego-narodzenia-nfz-podpowiada,8870.html",
                  ())
RPP = page("rpp", "Rzecznik Praw Pacjenta, the contact details at the foot of its pages on gov.pl",
           "https://www.gov.pl/web/rpp/teleplatforma-pierwszego-kontaktu-czyli-pomoc-poza-godzinami-pracy-przychodni",
           ("800 190 590", "ca\u0142odobowo"))
RIGHTS_CHAPTERS = (
    ("chpt_2", "Prawo pacjenta do \u015bwiadcze\u0144 zdrowotnych"),
    ("chpt_3", "Prawo pacjenta do informacji"),
    ("chpt_3a", "Prawo do zg\u0142aszania dzia\u0142a\u0144 niepo\u017c\u0105danych produkt\u00f3w leczniczych"),
    ("chpt_4", "Prawo pacjenta do tajemnicy informacji z nim zwi\u0105zanych"),
    ("chpt_5", "Prawo pacjenta do wyra\u017cenia zgody na udzielenie \u015bwiadcze\u0144 zdrowotnych"),
    ("chpt_6", "Prawo do poszanowania intymno\u015bci i godno\u015bci pacjenta"),
    ("chpt_7", "Prawo pacjenta do dokumentacji medycznej"),
    ("chpt_8", "Prawo pacjenta do zg\u0142oszenia sprzeciwu wobec opinii albo orzeczenia lekarza"),
    ("chpt_9", "Prawo pacjenta do poszanowania \u017cycia prywatnego i rodzinnego"),
    ("chpt_10", "Prawo pacjenta do opieki duszpasterskiej"),
    ("chpt_11", "Prawo pacjenta do przechowywania rzeczy warto\u015bciowych w depozycie"),
)
KIT_WORDS = "apteczk\u0119 dora\u017anej pomocy"


def with_must(a_page, *must):
    out = dict(a_page)
    out["must"] = tuple(must)
    return out


# Each fact: what it is about, what it says in this skill's own words, the numbers it gives, and what it rests on.
FACTS = (
    {"key": "emergency-numbers", "topic": "emergency", "title": "Emergency numbers in Poland",
     "says": "112 is the one emergency number for every rescue service. 999 reaches the ambulance service (medical dispatch), "
             "998 the State Fire Service and 997 the police. For an immediate threat to life or health, NFZ says to call an "
             "ambulance on 112 or 999.",
     "numbers": (("112", "every emergency service"), ("999", "ambulance, medical dispatch"), ("998", "State Fire Service"),
                 ("997", "police")),
     "sources": (
         law(NUMBER_PLAN, "par. 9 pkt 1 lit. a, pkt 3 lit. a", "DU/2024/1862", units=(
             ("para_9-pint_3-lett_a", "112 - wsp\u00f3lny numer alarmowy dla wszystkich s\u0142u\u017cb ustawowo powo\u0142anych do niesienia pomocy"),
             ("para_9-pint_1-lett_a", "997 - Policja, 998 - Pa\u0144stwowa Stra\u017c Po\u017carna, 999 - pogotowie ratunkowe - dyspozytornie medyczne"))),
         with_must(NFZ_SUDDEN, "112 lub 999"),
     )},
    {"key": "night-care", "topic": "care", "title": "Night and holiday care (nocna i \u015bwi\u0105teczna opieka zdrowotna)",
     "says": "For a sudden illness, or a sudden turn for the worse, that is not an emergency and should not wait for the GP "
             "surgery to open. The points are open from 18:00 to 08:00 the next day from Monday to Friday, and round the clock "
             "on Saturdays, Sundays and public holidays. No referral and no booking are needed, and there is no catchment "
             "area: any point sees a patient, wherever they live. It is free under health insurance. The doctor on duty "
             "advises in the point, by telephone, or at home where there are medical grounds; a nurse gives care in the point "
             "or, on the same grounds, at home. A sick note where there are medical grounds, and e-prescriptions for the "
             "medicines needed, can be given. It does not do follow-up visits, repeat prescriptions for long-term medicines "
             "or health certificates. NFZ says the addresses are on pacjent.gov.pl; its helpline names the nearest point.",
     "numbers": (),
     "sources": (
         law_by_hand(CARE, "art. 5 pkt 17a", "DU/2025/1461",
                     "nocna i \u015bwi\u0105teczna opieka zdrowotna - \u015bwiadczenia opieki zdrowotnej z zakresu podstawowej opieki zdrowotnej "
                     "udzielane przez \u015bwiadczeniodawc\u00f3w poza godzinami pracy okre\u015blonymi w umowach o udzielanie \u015bwiadcze\u0144 "
                     "podstawowej opieki zdrowotnej, w szczeg\u00f3lno\u015bci w dni wolne od pracy i w \u015bwi\u0119ta, w przypadku nag\u0142ego "
                     "zachorowania lub nag\u0142ego pogorszenia stanu zdrowia \u015bwiadczeniobiorcy, kt\u00f3re nie jest stanem nag\u0142ym;"),
         with_must(NFZ_SUDDEN, "od 18:00 do 8:00 nast\u0119pnego dnia (od poniedzia\u0142ku do pi\u0105tku)",
                   "przez ca\u0142\u0105 dob\u0119 (w soboty, niedziele oraz dni ustawowo wolne od pracy)", "Nie trzeba skierowania",
                   "Nie obowi\u0105zuje te\u017c rejonizacja"),
     )},
    {"key": "emergency-department", "topic": "care",
     "title": "Hospital emergency department (SOR) and admissions room (izba przyj\u0119\u0107)",
     "says": "For a threat to life or health: NFZ's examples are an accident, an injury, a poisoning, bleeding from the "
             "gut or the urinary tract. No referral is needed, and any of them takes a patient, wherever they live. People are seen in the order of how ill they are, as the staff "
             "judge it, and not in the order they came. It is there to find out what is wrong and steady the patient, not "
             "to stand in for a GP or a specialist clinic.",
     "numbers": (),
     "sources": (with_must(NFZ_SUDDEN, "Szpitalne Oddzia\u0142y Ratunkowe", "bez skierowania, niezale\u017cnie od miejsca swego zamieszkania"),)},
    {"key": "helpline", "topic": "care", "title": "Patient helpline (Telefoniczna Informacja Pacjenta)",
     "says": "800 190 590: free, round the clock, every day. NFZ's consultants say where the nearest hospital or night "
             "and holiday care point is. The Patient Ombudsman's office gives the same number as its own.",
     "numbers": (("800 190 590", "patient helpline of NFZ and the Patient Ombudsman, free, round the clock"),),
     "sources": (
         with_must(NFZ_SUDDEN, "Bezp\u0142atna i ca\u0142odobowa infolinia Narodowego Funduszu Zdrowia", "800 190 590"),
         RPP,
     )},
    {"key": "waiting-times", "topic": "care", "title": "Waiting times for treatment",
     "says": "Not in this file, on purpose: hospitals and clinics report their waiting lists to NFZ every week, so a copy "
             "would soon be wrong. NFZ's own service for them is at https://terminyleczenia.nfz.gov.pl.",
     "numbers": (),
     "sources": (
         page("nfz-open-data", "NFZ, \"Projekt Otwarte dane - dost\u0119p, standard, edukacja - API Terminy Leczenia\"",
              "https://www.nfz.gov.pl/o-nfz/programy-i-projekty/projekt-otwarte-dane-dostep-standard-edukacja-api-terminy-leczenia,10.html",
              ("przekazywania co tydzie\u0144", "dat\u0119 pierwszego wolnego terminu")),
         page("nfz-terminy", "NFZ, the waiting times service", "https://terminyleczenia.nfz.gov.pl/", ("Terminy leczenia",)),
     )},
    {"key": "patients-rights", "topic": "rights", "title": "A patient's rights",
     "says": "The act sets them out chapter by chapter. A patient has the right to health services; to information; to "
             "report the side effects of medicines; to confidentiality; to give or refuse consent to treatment; to "
             "intimacy and dignity; to their medical records; to object to a doctor's opinion or ruling; to private and "
             "family life; to pastoral care; and to have valuables kept in deposit. The Patient Ombudsman (Rzecznik "
             "Praw Pacjenta) has a chapter of the act to itself, and its office is reached on 800 190 590.",
     "numbers": (),
     "sources": (
         law(RIGHTS, "the titles of chapters 2 to 12", "DU/2024/581", base="DU/2009/417",
             units=RIGHTS_CHAPTERS + (("chpt_12", "Rzecznik Praw Pacjenta"),)),
         RPP,
     )},
    {"key": "old-medicines", "topic": "medicines", "title": "Getting rid of old medicines",
     "says": "Every municipality has to run collection points for sorted household waste (punkt selektywnego zbierania "
             "odpad\u00f3w komunalnych, PSZOK by its initials) that take expired medicines, and the needles and syringes left "
             "over from injections and blood tests done at home.",
     "numbers": (),
     "sources": (law_by_hand(WASTE, "art. 3 ust. 2 pkt 6", "DU/2025/733",
                             "tworz\u0105 w spos\u00f3b umo\u017cliwiaj\u0105cy \u0142atwy dost\u0119p wszystkim mieszka\u0144com gminy punkty selektywnego zbierania "
                             "odpad\u00f3w komunalnych, kt\u00f3re zapewniaj\u0105 przyjmowanie co najmniej odpad\u00f3w komunalnych wymienionych w pkt 5, "
                             "odpad\u00f3w niebezpiecznych, przeterminowanych lek\u00f3w i chemikali\u00f3w, odpad\u00f3w niekwalifikuj\u0105cych si\u0119 do "
                             "odpad\u00f3w medycznych, kt\u00f3re powsta\u0142y w gospodarstwie domowym w wyniku przyjmowania produkt\u00f3w leczniczych "
                             "w formie iniekcji i prowadzenia monitoringu poziomu substancji we krwi, w szczeg\u00f3lno\u015bci igie\u0142 i "
                             "strzykawek [...]"),)},
    {"key": "car-first-aid-kit", "topic": "kit", "title": "A first-aid kit in a car",
     "says": "The regulation on vehicle equipment asks for a first-aid kit in a bus, a taxi, a lorry that carries people "
             "outside the cab, and a vehicle used for driving lessons and tests. Its list of what every motor vehicle "
             "carries names a fire extinguisher and no first-aid kit, so this regulation does not require one in a "
             "private car.",
     "numbers": (),
     "sources": (law(VEHICLES, "par. 18 ust. 1 pkt 5, par. 24 ust. 1 pkt 6, par. 40 ust. 2 pkt 6, par. 43 ust. 1 pkt 7; par. 11 ust. 1",
                     "DU/2024/502", base="DU/2003/262",
                     units=(("bran_III-chpt_5-para_18-pass_1-pint_5", KIT_WORDS), ("bran_III-chpt_7-para_24-pass_1-pint_6", KIT_WORDS),
                            ("bran_III-chpt_10-para_40-pass_2-pint_6", KIT_WORDS), ("bran_III-chpt_13-para_43-pass_1-pint_7", KIT_WORDS),
                            ("bran_III-chpt_2-para_11-pass_1-pint_14", "w ga\u015bnic\u0119 umieszczon\u0105 w miejscu \u0142atwo dost\u0119pnym")),
                     absent=(("bran_III-chpt_2-para_11", "apteczk"),)),)},
    {"key": "sale-categories", "topic": "medicines", "title": "How a medicine may be sold (kategoria dost\u0119pno\u015bci)",
     "says": "Every medicine allowed on the market has one of five categories. OTC: given without a prescription. Rp: on "
             "prescription. Rpz: on prescription, for restricted use. Rpw: on prescription, and holding narcotic or "
             "psychotropic substances. Lz: used only in hospital care. The register gives the category of each pack.",
     "numbers": (),
     "sources": (law_by_hand(PHARMA, "art. 23a ust. 1", "DU/2026/612",
                             "Produkty lecznicze dopuszczone do obrotu otrzymuj\u0105 jedn\u0105 z nast\u0119puj\u0105cych kategorii dost\u0119pno\u015bci: "
                             "1) wydawane bez przepisu lekarza - OTC; 2) wydawane z przepisu lekarza - Rp; 3) wydawane z przepisu "
                             "lekarza do zastrze\u017conego stosowania - Rpz; 4) wydawane z przepisu lekarza, zawieraj\u0105ce \u015brodki "
                             "odurzaj\u0105ce lub substancje psychotropowe, okre\u015blone w odr\u0119bnych przepisach - Rpw; 5) stosowane "
                             "wy\u0142\u0105cznie w lecznictwie zamkni\u0119tym - Lz."),)},
    {"key": "icd-revision", "topic": "paperwork", "title": "Which revision of ICD is on Polish paperwork",
     "says": "The rules on medical records ask for the name and the statistical number of a diagnosis \"according to the "
             "International Classification of Diseases and Health Problems in force\", and name no revision. The Ministry "
             "of Health says that no date has been set for ICD-11 to come into force in Poland, and that one will be "
             "announced well ahead. So a code on Polish paperwork is still an ICD-10 code; that last step is this "
             "skill's reading of the two, and neither source says it in so many words.",
     "numbers": (),
     "sources": (
         law_by_hand(RECORDS, "par. 7 ust. 1", "DU/2026/1391",
                     "W dokumentacji wpisuje si\u0119 nazw\u0119 i numer statystyczny rozpoznania choroby, problemu zdrowotnego lub urazu, "
                     "wed\u0142ug obowi\u0105zuj\u0105cej Mi\u0119dzynarodowej Klasyfikacji Chor\u00f3b i Problem\u00f3w Zdrowotnych."),
         page("mz-icd11", "Ministerstwo Zdrowia, \"Odpowiedzi na zadawane pytania dotycz\u0105ce ICD-11\"",
              "https://www.gov.pl/web/zdrowie/pytania-i-odpowiedzi-icd-11",
              ("Informacja o terminie wdro\u017cenia b\u0119dzie podana do publicznej wiadomo\u015bci z odpowiednim wyprzedzeniem",)),
     )},
)
# what each category means, in this skill's words; the law's own are in the fact "sale-categories"
SALE = (("OTC", "given without a prescription"), ("Rp", "on prescription"), ("Rpz", "on prescription, for restricted use"),
        ("Rpw", "on prescription, holds narcotic or psychotropic substances"), ("Lz", "used only in hospital care"))
LICENCE_TEXT = """
region-pl.db: the Poland pack

Three kinds of thing are in this file. Each stays under its own terms.

1. The register of medicines

   Source: Rejestr Produkt\u00f3w Leczniczych (the register of medicinal products allowed on the market in
   Poland), kept by Centrum e-Zdrowia: https://rejestry.ezdrowie.gov.pl/rpl/search/public
   Licence: Creative Commons Attribution 4.0 International (CC BY 4.0),
   https://creativecommons.org/licenses/by/4.0/ , as stated for data set 397 on the open data portal of the
   Republic of Poland, https://dane.gov.pl/pl/dataset/397 . The portal adds the duty to say when the data
   was made and when it was obtained: the file is the state of the register at the end of the day before it
   was fetched, and the day it was fetched is in this database and in every answer drawn from it.
   Changes made: only medicines for people were kept, and of each only its name, the name of the substance,
   strength, form, route, ATC code, the holder of the permit, the sale category of its packs and the number of
   its leaflet. No wording was changed. Centrum e-Zdrowia does not endorse this skill.

2. Polish law

   Quoted word for word, with the article. Under art. 4 of the Polish act of 4 February 1994 on copyright and
   related rights, normative acts and official documents are not subject to copyright. The texts come from
   the Sejm's legislation service, https://api.sejm.gov.pl/eli .

3. Facts read on official pages

   Single facts (a telephone number, opening hours) from pages of NFZ, the Patient Ombudsman and the Ministry
   of Health. No sentence was copied from those pages: the facts are stated in this skill's own words, with
   the page named and the day it was read. The wording of every fact is this skill's, and is covered by the
   licence of the skill itself (MIT).
"""


# ---- the acts

def unit(html, uid, whole=False):
    """The text of one unit of an act as the Sejm's service lays it out: an article, a paragraph, a point, a
    chapter. By default only its own words, up to the first unit inside it or after it; with whole, everything
    inside it too. None if the act has no such unit."""
    m = re.search(r'<div class="unit unit_[a-z]+[^"]*" id="%s"' % re.escape(uid), html)
    if not m:
        return None
    end = len(html)
    for other in re.finditer(r'<div class="unit unit_[a-z]+[^"]*" id="([^"]+)"', html[m.end():]):
        if not whole or not other.group(1).startswith(uid + "-"):
            end = m.end() + other.start()
            break
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|td)>", "\n", html[m.start():end])
    # in this skill's typography, as every quotation is: straight quotes and the plain hyphen
    return desk.fix_text(" ".join(unescape(re.sub(r"(?s)<[^>]+>", " ", text)).split()))


def read_file(path, what):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        sys.exit("%s is not in the downloads folder: run with --fetch" % what)


def check_law(source, folder):
    """The words quoted from an act are looked up in the act itself. Returns the quotation."""
    html = read_file(os.path.join(folder, act_file(source["eli"])), "the act %s" % source["eli"])
    found = []
    for uid, words in source["units"]:
        text = unit(html, uid)
        if text is None or words not in text:
            sys.exit("the act %s no longer says \"%s\" where it did (%s): somebody has to read it again and put right "
                     "the fact that rests on it. Nothing was built" % (source["eli"], words, uid))
        if words not in found:
            found.append(words)
    for uid, words in source["absent"]:
        text = unit(html, uid, whole=True)
        if text is None or words in text:
            sys.exit("the act %s has changed where it was silent (%s): somebody has to read it again. Nothing was built"
                     % (source["eli"], uid))
    return "; ".join(found)


def check_newest(source, folder):
    """An act is only worth quoting while it is in force, and a consolidated text while it is the newest one.
    Returns a warning, or ''."""
    act = source.get("base") or source["eli"]
    try:
        with open(os.path.join(folder, act_file(act, ".json")), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        sys.exit("the description of the act %s is not in the downloads folder: run with --fetch" % act)
    if meta.get("inForce") != "IN_FORCE":
        sys.exit("the act %s is no longer in force: the fact that rests on it has to be read again. Nothing was built" % act)
    if not source.get("base"):
        return ""
    texts =[r.get("id") for r in (meta.get("references") or {}).get("Inf. o tek\u015bcie jednolitym", []) if r.get("id")]
    newest = sorted(texts, key=lambda i: tuple(int(n) for n in i.split("/")[1:]))[-1:] or [source["eli"]]
    if newest[0] != source["eli"]:
        return "a newer consolidated text of %s has been announced (%s): read it, and move the fact to it" % (source["base"], newest[0])
    return ""


def check_page(source, folder):
    text = read_file(os.path.join(folder, page_file(source["label"])), "the page %s" % source["url"])
    plain = " ".join(unescape(re.sub(r"(?s)<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text))).split())
    for words in source["must"]:
        if words not in plain:
            sys.exit("the page %s no longer says \"%s\": somebody has to read it again and put right the fact that rests "
                     "on it. Nothing was built" % (source["url"], words))


def act_file(eli, ending=".html"):
    return "pl-act-%s%s" % (eli.replace("/", "-"), ending)


def page_file(label):
    return "pl-page-%s.html" % label


def all_sources():
    for fact in FACTS:
        for source in fact["sources"]:
            yield fact, source


# ---- the register

def read_register(path):
    """[product, ...] for every medicine for people in the register's CSV file, and how many rows it had."""
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8-sig")
    except OSError:
        sys.exit("--register: no such file. Run with --fetch")
    except UnicodeDecodeError:
        sys.exit("the register file is not UTF-8: it is not the file the register publishes")
    rows = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    try:
        head = next(rows)
    except (StopIteration, csv.Error):
        sys.exit("the register file is empty")
    at = {}
    for key, name in COLUMNS.items():
        if name not in head:
            sys.exit("the register file has no column \"%s\": its shape has changed, and this script has to follow" % name)
        at[key] = head.index(name)
    products, total = [], 0
    try:
        for row in rows:
            if len(row) < len(head):
                continue
            total += 1
            if row[at["kind"]].strip() != HUMAN:
                continue
            get = lambda key: " ".join(row[at[key]].split())            # noqa: E731
            number = get("id")
            if not number.isdigit() or not get("name"):
                continue
            common = get("common")
            leaflet, imported = None, 0
            m = re.search(r"/medicinal-products/(\d+)/leaflet$", get("leaflet"))
            if m:
                leaflet = int(m.group(1))
            else:
                m = re.search(r"/medicinal-products/(\d+)/parallel-import-files/LEAFLET/public$", get("leaflet_import"))
                if m:
                    leaflet, imported = int(m.group(1)), 1
            products.append({
                "id": int(number), "name": get("name"), "common": common, "strength": "" if get("strength") == "-" else get("strength"),
                "form": get("form"), "route": get("route"), "atc": get("atc"), "holder": get("holder"),
                "sale": "; ".join(sale_of(row[at["packs"]])),
                # what is in it, spelt out, only where the register gives no one name for it
                "parts": get("parts") if (not common or common in NO_ONE_NAME) else "",
                "leaflet": leaflet, "imported": 1 if (imported or get("exported_from")) else 0})
    except csv.Error:
        sys.exit("the register file cannot be read as the semicolon-separated table it should be")
    return products, total


def sale_of(packs):
    """The sale categories among a product's packs. A pack is a line like '0590... | Rp | 5', and the size on
    the next line."""
    found = []
    for line in packs.splitlines():
        if "\u00a6" in line:
            for token in line.split("\u00a6")[:3]:
                token = token.strip()
                if re.fullmatch(r"[A-Za-z]{2,5}", token) and token not in found:
                    found.append(token)
    order = [code for code, _ in SALE]
    return sorted(found, key=lambda code: (order.index(code) if code in order else len(order), code))


# ---- fetching

def fetch_all(folder):
    os.makedirs(folder, exist_ok=True)
    dbtools.fetch(LICENCE_URL, LICENCE_FILE, "application/json", folder=folder)
    check_licence(os.path.join(folder, LICENCE_FILE))
    dbtools.fetch(REGISTER_URL, REGISTER_FILE, "text/csv", folder=folder)
    done = set()
    for _, source in all_sources():
        if source["kind"] == "page":
            if source["label"] not in done:
                done.add(source["label"])
                dbtools.fetch(source["url"], page_file(source["label"]), "text/html", folder=folder)
        elif not source.get("by_hand"):
            for eli, ending in ((source["eli"], ".html"), (source.get("base") or source["eli"], ".json")):
                if (eli, ending) not in done:
                    done.add((eli, ending))
                    dbtools.fetch(ELI + eli + ("/text.html" if ending == ".html" else ""), act_file(eli, ending),
                                  "text/html" if ending == ".html" else "application/json", folder=folder)


def check_licence(path, retrieved=None):
    """The open data portal's own entry for the register must still name the licence. Returns the day it was read."""
    try:
        with open(path, encoding="utf-8") as f:
            name = json.load(f)["data"]["attributes"]["license_name"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("the register's entry on the open data portal is not in the downloads folder, or cannot be read: run with "
                 "--fetch, or pass --licence-read with the day you read https://dane.gov.pl/pl/dataset/397 yourself")
    if name != LICENCE_NAME:
        sys.exit("the open data portal no longer gives the register's licence as %s (it says \"%s\"): read the terms again "
                 "before this data is passed on. Nothing was built" % (LICENCE_NAME, str(name)[:60]))
    return dbtools.origin(path, retrieved=retrieved)[1]


# ---- building

def build(a):
    folder = a.downloads
    out_folder = a.out or DATA
    register = a.register or os.path.join(folder, REGISTER_FILE)
    url, day = dbtools.origin(register, REGISTER_URL, a.retrieved)
    licence_day = core.a_date(a.licence_read, "--licence-read") if a.licence_read else check_licence(os.path.join(folder, LICENCE_FILE), a.retrieved)
    products, total = read_register(register)
    if len(products) < a.least:
        sys.exit("only %d medicines for people are in the register file, where some 20,000 are expected: it is not the whole "
                 "register. Nothing was built" % len(products))
    warnings, quotes, read_days = [], {}, {}
    for fact, source in all_sources():
        where = (fact["key"], fact["sources"].index(source))
        if source["kind"] == "page":
            check_page(source, folder)
            quotes[where], read_days[where] = "", dbtools.origin(os.path.join(folder, page_file(source["label"])), retrieved=a.retrieved)[1]
        elif source.get("by_hand"):
            quotes[where], read_days[where] = source["quote"], core.parse_date(READ)
        else:
            quotes[where] = check_law(source, folder)
            read_days[where] = dbtools.origin(os.path.join(folder, act_file(source["eli"])), retrieved=a.retrieved)[1]
            warning = check_newest(source, folder)
            if warning:
                warnings.append(warning)

    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        src = dbtools.add_source(con, "%s: the register of medicines allowed on the market in Poland (Centrum e-Zdrowia), the "
                                      "state at the end of the day before it was retrieved" % REGISTER_NAME, REGISTER_PAGE, day,
                                 "CC BY 4.0, as the open data portal dane.gov.pl states for data set 397 (read %s); the days the "
                                 "data was made and obtained are to be given" % licence_day.isoformat(), CREDIT)
        law_days = [d for w, d in read_days.items() if FACTS_BY_KEY[w[0]]["sources"][w[1]]["kind"] == "law"]
        page_days = [d for w, d in read_days.items() if FACTS_BY_KEY[w[0]]["sources"][w[1]]["kind"] == "page"]
        src_law = dbtools.add_source(con, "Polish law, as published in Dziennik Ustaw, from the Sejm's legislation service",
                                     "https://api.sejm.gov.pl/eli", min(law_days),
                                     "not under copyright: art. 4 of the Polish act on copyright and related rights (legal acts and "
                                     "official documents)", "")
        src_pages = dbtools.add_source(con, "Official pages of NFZ, the Patient Ombudsman and the Ministry of Health, read for "
                                            "single facts", "https://www.nfz.gov.pl", min(page_days),
                                       "no text is taken from them: single facts, in this skill's own words, with the page named", "")
        con.execute("CREATE TABLE word (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE)")
        # one row for a product as the register lists it; the long names that repeat are kept once, in 'word'
        con.execute("CREATE TABLE product (id INTEGER PRIMARY KEY, name TEXT NOT NULL, common INTEGER NOT NULL, strength TEXT NOT NULL, "
                    "form INTEGER NOT NULL, route INTEGER NOT NULL, atc TEXT NOT NULL, holder INTEGER NOT NULL, sale TEXT NOT NULL, "
                    "parts TEXT NOT NULL, leaflet INTEGER, imported INTEGER NOT NULL, source INTEGER NOT NULL)")
        con.execute("CREATE TABLE product_name (folded TEXT NOT NULL, product INTEGER NOT NULL, PRIMARY KEY (folded, product)) "
                    "WITHOUT ROWID")
        con.execute("CREATE TABLE sale (code TEXT PRIMARY KEY, means TEXT NOT NULL)")
        con.execute("CREATE TABLE fact (key TEXT PRIMARY KEY, position INTEGER NOT NULL, topic TEXT NOT NULL, title TEXT NOT NULL, "
                    "says TEXT NOT NULL)")
        # how: 'checked' when the build found the words in the source, 'by hand' when a person read them
        con.execute("CREATE TABLE fact_source (fact TEXT NOT NULL, position INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, "
                    "place TEXT NOT NULL, url TEXT NOT NULL, quote TEXT NOT NULL, read TEXT NOT NULL, how TEXT NOT NULL, "
                    "source INTEGER NOT NULL, PRIMARY KEY (fact, position)) WITHOUT ROWID")
        con.execute("CREATE TABLE number (code TEXT NOT NULL, position INTEGER NOT NULL, number TEXT NOT NULL, what TEXT NOT NULL, "
                    "fact TEXT NOT NULL, PRIMARY KEY (code, position)) WITHOUT ROWID")
        words = {}

        def word(text):
            if text not in words:
                words[text] = len(words) + 1
                con.execute("INSERT INTO word VALUES (?, ?)", (words[text], text))
            return words[text]
        names = 0
        for p in sorted(products, key=lambda p: (core.key(p["name"]), p["id"])):
            con.execute("INSERT OR IGNORE INTO product VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (p["id"], p["name"], word(p["common"]), p["strength"], word(p["form"]), word(p["route"]), p["atc"],
                         word(p["holder"]), p["sale"], p["parts"], p["leaflet"], p["imported"], src))
            folded = core.key(p["name"])
            if folded:
                names += con.execute("INSERT OR IGNORE INTO product_name VALUES (?, ?)", (folded, p["id"])).rowcount
        con.executemany("INSERT INTO sale VALUES (?, ?)", SALE)
        position = 0
        for n, fact in enumerate(FACTS, 1):
            con.execute("INSERT INTO fact VALUES (?, ?, ?, ?, ?)", (fact["key"], n, fact["topic"], fact["title"], fact["says"]))
            for at, source in enumerate(fact["sources"]):
                where = (fact["key"], at)
                by_hand = bool(source.get("by_hand"))
                address = source["url"] if source["kind"] == "page" else ELI + source["eli"] + ("/text.pdf" if by_hand else "/text.html")
                con.execute("INSERT INTO fact_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    fact["key"], at + 1, source["kind"], source["name"], source["place"], address, quotes[where],
                    read_days[where].isoformat(), "by hand" if by_hand else "checked", src_law if source["kind"] == "law" else src_pages))
            for number, what in fact["numbers"]:
                position += 1
                con.execute("INSERT INTO number VALUES (?, ?, ?, ?, ?)", (COUNTRY, position, number, what, fact["key"]))
        size = dbtools.finish(con, path, core.today(), facts=(
            ("format", 1), ("country", COUNTRY), ("products", len(products)), ("register-rows", total), ("names", names),
            ("facts", len(FACTS)), ("leaflet-url", LEAFLET), ("leaflet-url-import", LEAFLET_IMPORT),
            ("licence-read", licence_day.isoformat()), ("read-by-hand", READ)))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE_TEXT, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d medicines for people of %d rows in the register; %d names" % (len(products), total, names))
    say("          %d facts: %d sources checked against the act or the page, %d read by hand on %s" % (
        len(FACTS), sum(1 for _, s in all_sources() if not s.get("by_hand")), sum(1 for _, s in all_sources() if s.get("by_hand")), READ))
    for warning in warnings:
        say("WARNING   %s" % warning)
    say("          retrieved: register %s; licence entry read %s" % (day, licence_day))
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


FACTS_BY_KEY = dict((fact["key"], fact) for fact in FACTS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download everything into the downloads folder first (about 20 MB)")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--register", metavar="FILE", help="the register's CSV file (default: rpl.csv in the downloads folder)")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the files were downloaded, for files fetched by hand")
    ap.add_argument("--licence-read", metavar="DATE", help="for a build with no licence entry in the downloads folder: the day you "
                                                           "read https://dane.gov.pl/pl/dataset/397 yourself")
    ap.add_argument("--least", type=int, default=MIN_PRODUCTS, help=argparse.SUPPRESS)
    ap.add_argument("--out", metavar="DIR", help="where to write region-pl.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads)
    return build(a)


if __name__ == "__main__":
    main()
