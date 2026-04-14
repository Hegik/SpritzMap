# ![SpritzMap Logo](logo_big.svg)

SpritzMap zeigt dir, wo du in Berlin Aperol Spritz, Limoncello Spritz und Co. zu welchem Preis und in welchem Mischverhältnis bekommst.

## Die Karte lesen

Die Weinglas Symbole auf der Karte zeigen Bars und Biergärten mit erfassten Spritz-Preisen.
Die Farbe des Symbols entspricht der ausgewählten Spritz-Sorte.
Je kräftiger die Farbe, desto mehr Aperol (bzw. Likör) ist im Glas.

Orte für die noch keine Daten eingetragen wurden, werden mit einem "?" gekennzeichnet.

## Auswahl des Spritz-Getränks

Mit dem Filter unten (mobil) bzw. oben rechts (Desktop) kannst du:

- **Spritz-Sorte** wählen – z. B. Aperol, Limoncello oder Hugo
- **Preisstufe** filtern – €, €€ oder €€€

## Konto erstellen

Tippe oben rechts auf **„Anmelden"** und dann auf **„Noch kein Konto? Registrieren"**.
Nach der Registrierung erhältst du eine Bestätigungs-E-Mail.

## Preis hinzufügen

1. Tippe auf einen Ort auf der Karte.
2. Im Popup erscheint ein Button **„Spritz hinzufügen"** (nur für eingeloggte Nutzer).
3. Wähle die Sorte, trag den Preis ein und stelle das Mischverhältnis ein.
4. Speichern – fertig!
Wenn

## Mein Standort

Mit dem Standort-Button (◎) unten links auf der Karte springst du zu deiner aktuellen Position.

---

# FAQ

**Wieso ist mein lieblings Lokal nicht auf der Karte?**

Die Lokale werden einmal am Tag von OpenStreetMap abgerufen. Nur wenn ein Lokal dort hinterlegt ist, kann es in der Spritzmap vorkommen. 

**Wie berechnet sich die Einfärbung der Gebiete?**

Die Intensität ergibt sich aus zwei Faktoren: dem **Preis** und dem **Mischverhältnis** der erfassten Einträge im jeweiligen Gebiet.

Zuerst wird ein Preis-Score berechnet: Günstige Gebiete bekommen einen hohen Wert (nahe 1), teure einen niedrigen (nahe 0). Der Vergleich erfolgt logarithmisch – ein Unterschied von 5 € auf 6 € fällt stärker ins Gewicht als von 9 € auf 10 €. Anschließend wird dieser Wert mit dem durchschnittlichen Mischverhältnis der Einträge multipliziert – ein hoher Aperol-Anteil verstärkt die Einfärbung, ein niedriger schwächt sie ab. Das Ergebnis ist der **Spritz-Index** (0–100), der direkt die Deckkraft der Gebietsfarbe bestimmt.
