#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bibel_reparatur.py – repariert zwei Umlaut-Fehler in data/bibel/*.json

Fehler 1: Vor Wörtern, die mit Ä/Ö/Ü/ä/ö/ü beginnen, fehlt das Leerzeichen.
          "undüber" -> "und über",  "dieÄltesten" -> "die Ältesten"
Fehler 2: Am Versanfang fehlt der Umlaut-Großbuchstabe ganz.
          "ber die Stämme" -> "Über die Stämme"

Echte Zusammensetzungen (gegenüber, darüber, zwölf, Salböl, Völker …)
bleiben unangetastet.

Aufruf (im Ordner, in dem der Ordner "data" liegt):
    python bibel_reparatur.py              -> nur prüfen, Bericht schreiben
    python bibel_reparatur.py --anwenden   -> Dateien wirklich ändern
Optional anderer Ordner:  python bibel_reparatur.py --ordner pfad/zu/bibel
"""
import json, re, sys, shutil, datetime, collections
from pathlib import Path

UML_GROSS = "ÄÖÜ"
UML_KLEIN = "äöü"
# Wortanfänge, die mit einem folgenden "über…" ein echtes Wort bilden
SCHUTZ_PRAEFIX = {"gegen", "dar", "hin", "her", "wor", "hier", "vor", "dr", "drum",
                  "da", "Gegen", "Dar", "Hin", "Her", "Wor", "Hier", "Vor", "Dr"}
# Echte Wörter, die nie getrennt werden dürfen
SCHUTZ_WORT = {"Einöde", "Einöden", "obendrüber", "obendarüber", "Baumöl", "Freudenöl"}
# "eröffnen/eröffnet" (= offenbaren) ist ein echtes Wort; nur großes "Eröffnet" am
# Satzanfang ist "Er öffnet"
SCHUTZ_ANFANG = ("eröffn",)
# Kleingeschriebene Umlaut-Wortanfänge, die als eigenes Wort plausibel sind
KLEIN_START = ("über", "übel", "übrig", "übt", "üb", "öffn", "öd", "ärger",
               "äußer", "ähnlich", "ängst", "ächz", "ärm", "örter")

WORT = re.compile(r"[A-Za-zÄÖÜäöüß]+")


def lade(ordner):
    dateien = sorted(p for p in ordner.glob("*.json"))
    daten = {}
    for p in dateien:
        roh = p.read_text(encoding="utf-8")
        try:
            daten[p] = (roh, json.loads(roh))
        except json.JSONDecodeError as e:
            print(f"  übersprungen (kein gültiges JSON): {p.name}: {e}")
    return daten


def wortschatz(daten):
    """Alle Wörter, die irgendwo frei stehend vorkommen (mit Häufigkeit)."""
    z = collections.Counter()
    for _, (_, d) in daten.items():
        if not isinstance(d, list):
            continue
        for v in d:
            # erstes Wort des Verses nicht zählen (dort sitzt Fehler 2)
            for w in WORT.findall(str(v.get("text", "")))[1:]:
                z[w] += 1
    return z


def reparier_text(text, vok, gross_woerter):
    aenderungen = []

    # Fehler 2: Versanfang ohne Umlaut-Großbuchstaben ("ber die …")
    m = re.match(r"^([a-zß]+)\b", text)
    if m:
        frag = m.group(1)
        if vok[frag] <= 2:  # Bruchstück kommt sonst (fast) nie als Wort vor
            kandidaten = [u + frag for u in UML_GROSS if (u + frag) in gross_woerter]
            if not kandidaten:  # beide Fehler zugleich: "berdas" -> "Über das"
                kandidaten = [u + frag[:k] + " " + frag[k:] for u in UML_GROSS
                              for k in range(1, len(frag))
                              if (u + frag[:k]) in gross_woerter and vok[frag[k:]] >= 3]
            if len(kandidaten) == 1:
                neu = kandidaten[0]
                aenderungen.append((frag, neu))
                text = neu + text[len(frag):]

    # Fehler 1a: Großer Umlaut direkt nach Buchstabe oder Satzzeichen -> immer Fehler
    def gross(m):
        neu = m.group(1) + " " + m.group(2)
        aenderungen.append((m.group(0), neu))
        return neu
    text = re.sub(r"([A-Za-zÄÖÜäöüß]*[a-zäöüß.,;:!?)»«])([ÄÖÜ][A-Za-zÄÖÜäöüß]*)", gross, text)

    # "auf Über ihm" -> "auf über ihm": die Präposition steht nach einem
    # Kleinbuchstaben nie groß (Substantive wie "Übel" bleiben groß)
    def praep(m):
        neu = m.group(1) + " über"
        aenderungen.append((m.group(0), neu))
        return neu
    text = re.sub(r"([a-zäöüß]) Über\b", praep, text)

    # "er'süber" -> "er's über"
    def apo(m):
        neu = m.group(1) + " " + m.group(2)
        aenderungen.append((m.group(0), neu))
        return neu
    text = re.sub(r"(['’]s)([äöü][a-zäöüß]+)", apo, text)

    # Fehler 1b: kleiner Umlaut mitten im Wort, nur wenn beide Teile eigene Wörter sind
    def klein(m):
        wort = m.group(0)
        if wort in SCHUTZ_WORT or wort.startswith(SCHUTZ_ANFANG):
            return wort
        for i in range(2, len(wort)):
            if wort[i] in UML_KLEIN and wort[i - 1] not in UML_KLEIN:
                links, rechts = wort[:i], wort[i:]
                if links in SCHUTZ_PRAEFIX:
                    continue
                if not rechts.startswith(KLEIN_START):
                    continue
                ueber = rechts.startswith(("über", "übrig", "übel"))
                # bei "über/übrig/übel" reicht der Schutz-Präfix-Test; sonst muss der
                # linke Teil auch als eigenes Wort vorkommen
                if not ueber and vok[links] < 3:
                    continue
                aenderungen.append((wort, links + " " + rechts))
                return links + " " + rechts
        return wort
    text = WORT.sub(klein, text)
    return text, aenderungen


def main():
    args = sys.argv[1:]
    anwenden = "--anwenden" in args
    ordner = Path("data/bibel")
    if "--ordner" in args:
        ordner = Path(args[args.index("--ordner") + 1])
    if not ordner.is_dir():
        sys.exit(f"Ordner nicht gefunden: {ordner.resolve()}\n"
                 "Bitte im Repo-Hauptordner starten (dort, wo der Ordner 'data' liegt).")

    daten = lade(ordner)
    vok = wortschatz(daten)
    gross_woerter = {w for w in vok if w[0] in UML_GROSS}

    bericht = [f"Bibel-Reparatur {datetime.datetime.now():%Y-%m-%d %H:%M}  "
               f"({'ANGEWENDET' if anwenden else 'nur Prüfung'})", ""]
    summe = collections.Counter()
    geaendert = {}
    for p, (roh, d) in daten.items():
        if not isinstance(d, list):
            continue
        n = 0
        for v in d:
            if not isinstance(v, dict) or "text" not in v:
                continue
            neu, aend = reparier_text(v["text"], vok, gross_woerter)
            if aend:
                for alt, ers in aend:
                    bericht.append(f"{p.stem} {v.get('chapter')},{v.get('verse')}:  {alt}  ->  {ers}")
                    summe[(alt, ers)] += 1
                v["text"] = neu
                n += len(aend)
        if n:
            geaendert[p] = (roh, d, n)

    bericht += ["", "Zusammenfassung (häufigste Änderungen):"]
    bericht += [f"{c:5d} ×  {a}  ->  {b}" for (a, b), c in summe.most_common()]
    bericht += ["", f"Dateien mit Änderungen: {len(geaendert)} von {len(daten)}, "
                    f"Änderungen gesamt: {sum(x[2] for x in geaendert.values())}"]
    Path("bibel_reparatur_bericht.txt").write_text("\n".join(bericht), encoding="utf-8")

    if anwenden and geaendert:
        sicher = ordner.parent / f"bibel_sicherung_{datetime.datetime.now():%Y%m%d_%H%M%S}"
        shutil.copytree(ordner, sicher)
        for p, (roh, d, n) in geaendert.items():
            einr = 2 if roh.lstrip().startswith("[\n  {") or "\n  {" in roh[:20] else None
            txt = json.dumps(d, ensure_ascii=False, indent=einr)
            if roh.endswith("\n"):
                txt += "\n"
            p.write_text(txt, encoding="utf-8")
        print(f"Fertig. {len(geaendert)} Dateien geändert. Sicherung: {sicher}")
    else:
        print(f"Prüfung fertig: {sum(x[2] for x in geaendert.values())} Änderungen in "
              f"{len(geaendert)} Dateien gefunden. Siehe bibel_reparatur_bericht.txt")
        if geaendert:
            print("Zum Anwenden:  python bibel_reparatur.py --anwenden")


if __name__ == "__main__":
    main()
