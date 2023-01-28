"""Prevzemi podatke iz spleta ter jih shrani v formatu, primernem za kasnejšo obdelavo."""


"""
Prevzemanje podatkov poteka v treh fazah.
V prvi fazi poiščemo seznam vseh literarnih del na strani wikivir, ki jih bomo potencialno prenesli.
V drugi fazi za vsako od teh del prenesemo besedilo iz wikivira.
V tretji fazi poskusimo za vsako od del z najdenim besedilom poiskati še metapodatke na dlib.si

Drugo in tretjo fazo lahko paraleliziramo; samo paziti moramo, da za posamično literarno delo prvo izvedemo drugo fazo, nato tretjo.
"""

import asyncio
import requests
import re
from collections.abc import Iterable
import os
import csv

from obdelava_xml_podatkov import obdelaj_besede


# čas med zaporednimi zahtevki na isto spletno stran, v sekundah
CAS_SPANJA = 1

# imena datotek, kjer se shranijo podatki
IME_DATOTEKE_PRVE_FAZE = "podatki/literarne_strani"
IMENA_DATOTEK_DRUGE_FAZE = "podatki/stran{:0>5}"
IME_DATOTEKE_BESED = "podatki/accented_sloleks2.xml"
IME_IZHODNE_DATOTEKE_BESED = "obdelani_podatki/besede.csv"
IME_DATOTEKE_DRUGE_FAZE = "obdelani_podatki/podatki.csv"
IME_DATOTEKE_KATEGORIJ = "obdelani_podatki/kategorije.csv"
IME_VHODNE_DATOTEKE_TRETJE_FAZE = "podatki/viri.csv"
IMENA_DATOTEK_VIROV = "podatki/vir{:0>5}"
IME_DATOTEKE_VIROV = "obdelani_podatki/viri.csv"


REGEX_POISCI_KATEGORIJE = re.compile(r'<a href="/wiki/Posebno:Kategorije" title="Posebno:Kategorije">[A-Za-z]+</a>: <ul>(.+)</ul></div><div id="mw-hidden-catlinks"')
REGEX_POISCI_IMENA_KATEGORIJ = re.compile(r'<li><a [^>]+>([^<]+)</a>')
REGEX_POISCI_VSEBINO_STRANI = re.compile(r'<div class="mw-parser-output">(.*)<!-- \nNewPP', re.DOTALL)
REGEX_POISCI_ODSTAVKE = re.compile(r'<p>([^<]+)</p>')
REGEX_POISCI_AVTORJA = re.compile(r'<i><a [^>]+>([^<]+)</a></i>')
REGEX_POISCI_NASLOV = re.compile(r'<b>([^<]+)</b>')
REGEX_TABELA = re.compile(r'<table class="wikitable"[^>]+>(.*?)</table>')
REGEX_LETNICA = re.compile(r'\b([12][0-9]{3})\b')
REGEX_DLIB = re.compile(r'(https?://www\.dlib\.si/\?[^"]+)')
REGEX_COBBIS = re.compile(r'(https?://plus\.cobiss\.si/[^"]+)')
REGEX_VIR_DLIB = re.compile(r'<div class="[^"]+">Vir</div><div class="[^"]+">(<a href="[^"]+"></a>)?<a href="[^"]+">([^<]+)</a>')
REGEX_VIR_COBISS = re.compile(r'<span>Vrsta gradiva</span> - (.+)')


async def zapisi_v_datoteko(ime_datoteke, podatki, nacin="a"):
    """Asinhrono zapiši podatke v datoteko. Če je 'podatki' string,
    ga zapiši dobesedno; če je 'podatki' iterable, ga zapiši kot seznam
    vrstic."""
    with open(ime_datoteke, nacin) as f:
        if isinstance(podatki, str):
            f.write(podatki)
        elif isinstance(podatki, Iterable):
            f.write("\n".join(podatki))
        else:
            raise ValueError("'podatki' mora biti string ali iterable")


async def poisci_seznam_literarnih_del(ime_datoteke=None, verbose=False):
    """Poišči seznam vseh literarnih del, in ga shrani v ime_datoteke. Vrni seznam."""

    # osnovni URL za pridobitev člankov
    OSNOVNI_URL = "https://sl.wikisource.org/w/index.php?title=Posebno:VseStrani"

    OSNOVNI_LITERARNI_URL = "https://sl.wikisource.org/wiki/"

    """Število člankov na stran je omejeno; za zbiranje vseh člankov
    je potrebnih več obiskov. K sreči vsaka stran vsebuje tudi povezavo do
    naslednje strani, ki jo lahko direktno uporabimo."""

    # regularni izraz za iskanje povezave do naslednjega seznama
    NASLEDNJI_URL_REGEX = r'<a href="/w/index\.php\?title=Posebno:VseStrani&amp;from=([^"]+)" title="Posebno:VseStrani">Naslednja stran'

    # regularni izraz za iskanje literarnih del na seznamu
    LITERARNA_STRAN_REGEX = r'<a href="/wiki/([^"]+)"( class="mw-redirect")? title="[^"]+">[^<]+</a>'

    # na začetku moramo pobrisati datoteko, da ne zapisujemo česa dvakrat:
    if ime_datoteke is not None:
        await zapisi_v_datoteko(ime_datoteke, "", "w")

    # Seznam hrani povezave do literatnih člankov
    povezave = []

    naslednji_url = OSNOVNI_URL
    while naslednji_url is not None:

        if verbose:
            print()
            print("Obiskujem", naslednji_url)

        resp = requests.get(naslednji_url)

        # poišči nov url
        m = re.search(NASLEDNJI_URL_REGEX, resp.text)
        if not m:
            print("Iskanje naslov del se je končalo. Zadnja obiskana stran:", naslednji_url)
            naslednji_url = None
        else:
            naslednji_url = OSNOVNI_URL + "&from=" + m.group(1)

        # poišči literarna dela in si jih shrani
        # pri tem smo morda našli povezavo, pisano poševno (class="mw-redirect")
        # ali pa ne. Tega podatka ne potrebujemo.
        povezave_te_strani = re.findall(LITERARNA_STRAN_REGEX, resp.text)
        povezave_te_strani = list(map(lambda par: OSNOVNI_LITERARNI_URL + par[0], povezave_te_strani))

        if verbose:
            print(f"Našel {len(povezave_te_strani)} povezav")

        povezave.extend(povezave_te_strani)

        # Preden preiščemo novo stran, se malce spočijemo
        # ta čas lahko uporabimo za zapisovanje v datoteko
        if ime_datoteke is None:
            await asyncio.sleep(CAS_SPANJA)
        else:
            await asyncio.gather(
                zapisi_v_datoteko(ime_datoteke, povezave_te_strani),
                asyncio.sleep(CAS_SPANJA)
            )

    return povezave


def pridobi_shranjen_seznam_literarnih_del(ime_datoteke):
    """Preberi vnaprej shranjen seznam literarnih del iz diska."""
    with open(ime_datoteke) as f:
        povezave = [ln.strip() for ln in f if ln.strip()]
    return povezave


async def poisci_besedilo_literarnega_dela(povezava, ime_datoteke, verbose=False, header=""):
    """Poišči html besedilo na dani povezavi in ga shrani v datoteko"""
    if verbose:
        print(f"Obiskujem {povezava}.")

    try:
        resp = requests.get(povezava)
        if resp.status_code != 200:
            print(f"Stran {povezava} je vrnila kodo {resp.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"Napaka pri pridobivanju strani {povezava}")
        print("Spim 3 sekunde, nato nadaljujem.")
        await asyncio.sleep(3)
        return False

    with open(ime_datoteke, "w") as f:
        f.write(header)
        f.write(povezava + "\n\n")
        f.write(resp.text)

    return True


async def poisci_kategorije(vsebina):
    """Poišči kategorije v vsebini strani"""

    m = re.search(REGEX_POISCI_KATEGORIJE, vsebina)
    if not m:
        return []

    podvsebina = m.group(1)
    return re.findall(REGEX_POISCI_IMENA_KATEGORIJ, podvsebina)


def preskoci_stran(kategorije, verbose=False):
    """Na podlagi kategorij določi, če naj se neka stran izpusti"""

    if not kategorije:
        if verbose:
            print("Preskok zaradi praznih kategorij")
        return True

    for kategorija in kategorije:

        if kategorija.startswith("Dela v ") and kategorija != "Dela v slovenščini":
            if verbose:
                print(f"Preskok zaradi kategorije {kategorija}")
            return True

        if "Nemške" in kategorija or "nemške" in kategorija:
            if verbose:
                print(f"Preskok zaradi kategorije {kategorija}")
            return True

        if kategorija.startswith("Avtorji") or kategorija.startswith("Rojeni") or kategorija.startswith("Umrli"):
            if verbose:
                print(f"Preskok zaradi kategorije {kategorija}")
            return True

    return False


async def pridobi_vsebinske_podatke(vsebina):

    m = re.search(REGEX_POISCI_VSEBINO_STRANI, vsebina)
    if not m:
        return None

    vsebina_strani = m.group(1)
    predelana_vsebina = vsebina_strani\
        .replace("<br />", "\n").replace("<br>", "\n")

    besedilo = "\n".join(
        map(str.strip, re.findall(REGEX_POISCI_ODSTAVKE, predelana_vsebina))
    )

    if not besedilo.strip():
        return None

    avtor_match = re.search(REGEX_POISCI_AVTORJA, vsebina_strani)
    if not avtor_match:
        # dovoljujemo tudi dela brez avtorja
        avtor = ""
    else:
        avtor = avtor_match.group(1)

    naslov_match = re.search(REGEX_POISCI_NASLOV, vsebina_strani)
    if not naslov_match:
        return None
    naslov = naslov_match.group(1)

    # Letnico iščemo samo v tabeli na začetku, ter v naslovu
    # prvo pogledamo naslov; s tem najdemo strani kot https://sl.wikisource.org/wiki/Stran:Slovenske_vecernice_1865.djvu/27
    letnica_match = re.search(REGEX_LETNICA, naslov)
    if letnica_match is None:
        tabela = re.search(REGEX_TABELA, vsebina_strani)
        if tabela is None:
            # lahko se zgodi, da tabele ni; takrat tudi ni letnice v tabeli
            letnica = -1
        else:
            letnica_match = re.search(REGEX_LETNICA, tabela.group(1))
            if letnica_match:
                letnica = int(letnica_match.group(1))
            else:
                letnica = -1
    else:
        # če smo našli letnico že v naslovu
        letnica = int(letnica_match.group(1))

    podatek = {
        "besedilo": besedilo,
        "avtor": avtor,
        "naslov": naslov,
        "letnica": letnica
    }

    vir_match = re.search(REGEX_DLIB, vsebina_strani)
    if vir_match:
        podatek["vir"] = vir_match.group(1)

    vir_match = re.search(REGEX_COBBIS, vsebina_strani)
    if vir_match:
        podatek["vir"] = vir_match.group(1)

    return podatek


async def obdelaj_stran(indeks, verbose=False):
    """Obdelaj shranjeno stran z danim indeksom. Vrni zbrane podatke o njem."""
    ime_datoteke = IMENA_DATOTEK_DRUGE_FAZE.format(indeks)

    if not os.path.exists(ime_datoteke):
        # napaka pri pridobivanju
        if verbose:
            print(f"Datoteka {ime_datoteke} ne obstaja.")
        return

    with open(ime_datoteke) as f:
        vsebina = f.read()

    povezava = vsebina[:vsebina.find('\n')]

    # Poišči kategorije, ki nam bodo pomagale v prihodnje
    kategorije = await poisci_kategorije(vsebina)

    if verbose:
        print(f"Kategorije s strani {povezava}: {kategorije}")

    if preskoci_stran(kategorije, verbose):
        return None

    vsebinski_podatki = await pridobi_vsebinske_podatke(vsebina)

    if vsebinski_podatki is None:
        return None

    vsebinski_podatki.update({
        "povezava": povezava,
        "kategorije": kategorije
    })

    for kategorija in kategorije:
        m = re.search(REGEX_LETNICA, kategorija)
        if m:
            vsebinski_podatki["letnica"] = int(m.group(1))
            if verbose:
                print(f"Določena letnica iz kategorije `{kategorija}`: {m.group(1)}")

    return vsebinski_podatki


async def poisci_besedila_literarnih_del(povezave, ime_datoteke_podatkov, ime_datoteke_kategorij, ime_datoteke_virov, verbose=False):
    """Poišči besedila za vsa literarna dela, našteta v povezavah"""

    vsi_podatki = []

    for i, povezava in enumerate(povezave):
        ime_datoteke = IMENA_DATOTEK_DRUGE_FAZE.format(i)

        if not os.path.exists(ime_datoteke):
            await asyncio.gather(
                poisci_besedilo_literarnega_dela(
                    povezava, ime_datoteke, verbose
                ),
                asyncio.sleep(CAS_SPANJA)
            )

        podatki = await obdelaj_stran(i, verbose)

        if podatki is None:
            # Izpusti stran
            continue

        vsi_podatki.append(podatki)

    with open(ime_datoteke_podatkov, "w") as f:
        writer = csv.DictWriter(
            f,
            ["povezava", "naslov", "avtor", "besedilo", "letnica"],
            extrasaction="ignore"
        )
        for podatek in vsi_podatki:
            writer.writerow(podatek)

    with open(ime_datoteke_kategorij, "w") as f:
        writer = csv.writer(f)
        for podatek in vsi_podatki:
            for kategorija in podatek["kategorije"]:
                writer.writerow([podatek["povezava"], kategorija])

    with open(ime_datoteke_virov, "w") as f:
        writer = csv.writer(f)
        for podatek in vsi_podatki:
            if "vir" in podatek:
                writer.writerow([podatek["povezava"], podatek["vir"]])

    return vsi_podatki


def pridobi_vir_dlib(besedilo):
    m = re.search(REGEX_VIR_DLIB, besedilo)
    if not m:
        return None
    return m.group(2)


def pridobi_vir_cobiss(besedilo):
    m = re.search(REGEX_VIR_COBISS, besedilo)
    if not m:
        return None
    return m.group(1)


async def poisci_podatke_virov(ime_vhodne_datoteke, ime_izhodne_datoteke, verbose=False):
    """Poišči podatke drugih virov (dlib/cobiss)"""

    # Prvo pridobi vso besedilo iz interneta
    datoteke_za_procesiranje = []
    with open(ime_vhodne_datoteke) as f:
        reader = csv.reader(f)
        indeks = 0
        for wikivir_povezava, druga_povezava in reader:
            ime_datoteke = IMENA_DATOTEK_VIROV.format(indeks)
            if not os.path.exists(ime_datoteke):
                if "{{{ID}}}" not in druga_povezava:
                    uspeh = await poisci_besedilo_literarnega_dela(
                        druga_povezava,
                        IMENA_DATOTEK_VIROV.format(indeks),
                        header=f"{wikivir_povezava}\n"
                    )
                    if uspeh:
                        datoteke_za_procesiranje.append(ime_datoteke)
                    await asyncio.sleep(CAS_SPANJA)

            else:  # path exists
                datoteke_za_procesiranje.append(ime_datoteke)
            indeks += 1

    # Ko imamo besedilo, ga sprocesiramo
    gradiva = []
    for ime_datoteke in datoteke_za_procesiranje:
        with open(ime_datoteke) as f:
            povezava_clanka = f.readline().strip()
            povezava_vira = f.readline().strip()
            besedilo = f.read()

            if "dlib" in povezava_vira:
                vir = pridobi_vir_dlib(besedilo)
            else:
                vir = pridobi_vir_cobiss(besedilo)

            if vir is not None:
                gradiva.append((povezava_clanka, vir))

    with open(ime_izhodne_datoteke, "w") as f:
        writer = csv.writer(f)
        writer.writerows(gradiva)


def pridobi_podatke(verbose=False, prva_faza=True, datoteka_prve_faze=IME_DATOTEKE_PRVE_FAZE, druga_faza=True, datoteka_druge_faze=IME_DATOTEKE_DRUGE_FAZE, datoteka_kategorij=IME_DATOTEKE_KATEGORIJ, datoteka_virov=IME_VHODNE_DATOTEKE_TRETJE_FAZE, tretja_faza=True, izhodna_datoteka_virov=IME_DATOTEKE_VIROV):
    """Pomožna funkcija, ki v pravem zaporedju pridobi vse podatke."""
    if prva_faza:
        if verbose:
            print("Pridobivanje prve faze iz interneta.")

        povezave = asyncio.run(
            poisci_seznam_literarnih_del(
                ime_datoteke=datoteka_prve_faze,
                verbose=verbose
            )
        )
    else:  # not prva_faza
        if verbose:
            print("Pridobivanje prve faze iz diska.")

        povezave = pridobi_shranjen_seznam_literarnih_del(datoteka_prve_faze)

    print(f"Prva faza dokončana. Naloženih {len(povezave)} povezav.")

    if druga_faza:
        vsi_podatki = asyncio.run(poisci_besedila_literarnih_del(povezave, datoteka_druge_faze, datoteka_kategorij, datoteka_virov, verbose))
        print(f"Druga faza dokončana. Ohranjenih {len(vsi_podatki)} del.")

        stevec = 0
        for podatek in vsi_podatki:
            if podatek["letnica"] > 0:
                stevec += 1
        print(f"Število del z letnico je {stevec}")

    if tretja_faza:
        podatki_virov = asyncio.run(poisci_podatke_virov(datoteka_virov, izhodna_datoteka_virov, verbose))


if __name__ == "__main__":
    import argparse
    import shutil

    parser = argparse.ArgumentParser(description="Pridobi podatke o literarnih delih.")
    parser.add_argument("--verbose", action="store_const", const=True, default=False)
    parser.add_argument("--prva-faza", action="store_const", const=True, default=False)
    parser.add_argument("--druga-faza", action="store_const", const=True, default=False)
    parser.add_argument("--tretja-faza", action="store_const", const=True, default=False)
    parser.add_argument("--vse-faze", action="store_const", const=True, default=False)
    parser.add_argument("--besede", action="store_const", const=True, default=False)

    args = parser.parse_args()

    if args.vse_faze:
        args.prva_faza = True
        args.druga_faza = True
        args.tretja_faza = True

    if not any((args.prva_faza, args.druga_faza, args.tretja_faza, args.besede)):
        print("Nič ni za storiti.")
        quit()

    try:
        shutil.copy(IME_DATOTEKE_PRVE_FAZE, IME_DATOTEKE_PRVE_FAZE + "_backup")
        shutil.copy(IME_DATOTEKE_DRUGE_FAZE, IME_DATOTEKE_DRUGE_FAZE + "_backup")
        shutil.copy(IME_DATOTEKE_KATEGORIJ, IME_DATOTEKE_KATEGORIJ + "_backup")
    except FileNotFoundError:
        # če ni datoteke za backup, je pač ne bomo kopirali
        pass

    pridobi_podatke(
        verbose=args.verbose,
        prva_faza=args.prva_faza,
        druga_faza=args.druga_faza,
        tretja_faza=args.tretja_faza
    )

    if args.besede:
        # predelaj XML datoteko z besedami
        obdelaj_besede(IME_DATOTEKE_BESED, IME_IZHODNE_DATOTEKE_BESED)
