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


# čas med zaporednimi zahtevki na isto spletno stran, v sekundah
CAS_SPANJA = 1
IME_DATOTEKE_PRVE_FAZE = "podatki/literarne_strani"


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


def pridobi_podatke(verbose=False, prva_faza=True, datoteka_prve_faze=IME_DATOTEKE_PRVE_FAZE):
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
    else:
        if verbose:
            print("Pridobivanje prve faze iz diska.")

        povezave = pridobi_shranjen_seznam_literarnih_del(datoteka_prve_faze)

    print(f"Prva faza dokončana. Naloženih {len(povezave)} povezav.")


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

    # ustvari backup vseh datotek
    shutil.copy(IME_DATOTEKE_PRVE_FAZE, IME_DATOTEKE_PRVE_FAZE + "_backup")

    pridobi_podatke(
        verbose=args.verbose,
        prva_faza=args.prva_faza
    )
