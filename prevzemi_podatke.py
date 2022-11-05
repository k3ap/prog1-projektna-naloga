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


# čas med zaporednimi zahtevki na isto spletno stran, v sekundah
CAS_SPANJA = 1

# imena datotek, kjer se shranijo podatki
IME_DATOTEKE_PRVE_FAZE = "podatki/literarne_strani"
IMENA_DATOTEK_DRUGE_FAZE = "podatki/stran{:0>5}"


REGEX_POISCI_KATEGORIJE = re.compile(r'<a href="/wiki/Posebno:Kategorije" title="Posebno:Kategorije">[A-Za-z]+</a>: <ul>(.+)</ul></div><div id="mw-hidden-catlinks"')
REGEX_POISCI_IMENA_KATEGORIJ = re.compile(r'<li><a [^>]+>([^<]+)</a>')
REGEX_POISCI_VSEBINO_STRANI = re.compile(r'<div class="mw-parser-output">(.*)<!-- \nNewPP', re.DOTALL)
REGEX_POISCI_ODSTAVKE = re.compile(r'<p>([^<]+)</p>')
REGEX_POISCI_AVTORJA = re.compile(r'<i><a [^>]+>([^<]+)</a></i>')
REGEX_POISCI_NASLOV = re.compile(r'<b>([^<]+)</b>')


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


async def poisci_besedilo_literarnega_dela(povezava, ime_datoteke, verbose=False):
    """Poišči html besedilo na dani povezavi in ga shrani v datoteko"""
    if verbose:
        print(f"Obiskujem {povezava}.")

    try:
        resp = requests.get(povezava)
        if resp.status_code != 200:
            print(f"Stran {povezava} je vrnila kodo {resp.status_code}")
            return

    except requests.exceptions.ConnectionError:
        print(f"Napaka pri pridobivanju strani {povezava}")
        print("Spim 3 sekunde, nato nadaljujem.")
        await asyncio.sleep(3)
        return

    with open(ime_datoteke, "w") as f:
        f.write(povezava + "\n\n")
        f.write(resp.text)


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

    return {
        "besedilo": besedilo,
        "avtor": avtor,
        "naslov": naslov
    }


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

    return vsebinski_podatki


async def poisci_besedila_literarnih_del(povezave, verbose=False):
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

    return vsi_podatki


def pridobi_podatke(verbose=False, prva_faza=True, datoteka_prve_faze=IME_DATOTEKE_PRVE_FAZE, druga_faza=True):
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
        vsi_podatki = asyncio.run(poisci_besedila_literarnih_del(povezave, verbose))
        print(f"Druga faza dokončana. Ohranjenih {len(vsi_podatki)} del.")


if __name__ == "__main__":
    import argparse
    import shutil

    parser = argparse.ArgumentParser(description="Pridobi podatke o literarnih delih.")
    parser.add_argument("--verbose", action="store_const", const=True, default=False)
    parser.add_argument("--prva-faza", action="store_const", const=True, default=False)
    parser.add_argument("--druga-faza", action="store_const", const=True, default=False)
    parser.add_argument("--tretja-faza", action="store_const", const=True, default=False)
    parser.add_argument("--vse-faze", action="store_const", const=True, default=False)

    args = parser.parse_args()

    if args.vse_faze:
        args.prva_faza = True
        args.druga_faza = True
        args.tretja_faza = True

    if not any((args.prva_faza, args.druga_faza, args.tretja_faza)):
        print("Nič ni za storiti. Uporabi --prva-faza, --druga-faza, --tretja-faza oz. --vse-faze za vključitev dela.")
        quit()

    shutil.copy(IME_DATOTEKE_PRVE_FAZE, IME_DATOTEKE_PRVE_FAZE + "_backup")

    pridobi_podatke(
        verbose=args.verbose,
        prva_faza=args.prva_faza
    )
