# ![SpritzMap Logo](logo_big.svg)

SpritzMap zeigt dir, wo du in deiner Stadt Aperol Spritz, Limoncello Spritz und Co. zu welchem Preis und in welchem Mischverhältnis bekommst.

## Die Karte 

Durch Scrollen oder Touch-Gesten kann durch die Karte navigiert werden. Bei näherer Zoomstufe werden die einzelnen Lokale als Spritzgläser angezeigt.

Die Spritz Symbole auf der Karte zeigen Bars und Biergärten mit erfassten Spritz-Preisen.
Die Farbe des Symbols entspricht der ausgewählten Spritz-Sorte.
Je kräftiger die Farbe, desto mehr Aperol (bzw. Likör) ist im Glas.

Orte für die noch keine Daten eingetragen wurden, werden mit einem "?" gekennzeichnet.

## Das Popup eines Lokals

Tippst du auf ein Lokal, siehst du:

- **Art des Lokals** (Bar, Biergarten, Café …)
- **Preis und Preisstufe** (€, €€ oder €€€) der gewählten Sorte
- **Mischverhältnis** – gemittelt aus allen aktuellen Meldungen, deren Anzahl darunter steht
- **Glasform**, in der der Spritz serviert wird
- die **Notiz** zur letzten Meldung, **weitere Sorten** mit ihren Preisen und **Fotos** (zum Vergrößern antippen)

Ist ein Preis noch aktuell, kannst du ihn mit **„Preis stimmt noch ✓"** bestätigen.

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
3. Wähle die Sorte und trag den Preis ein.
4. Optional: **Foto aufnehmen**. Die SpritzMap schlägt dir daraus Glasform und Mischverhältnis vor – ein Balken zeigt, wie weit die Analyse ist. Die Vorschläge sind mit **„KI-Vorschlag"** markiert und lassen sich jederzeit ändern.
5. Stelle das Mischverhältnis ein und wähle die **Glasform** (Weinglas, Wasserglas oder Sonstiges).
6. Speichern – fertig!

Das Mischverhältnis lässt sich am besten beurteilen, solange der Spritz noch vor dir steht. Deshalb prüft die SpritzMap beim Eintragen kurz deinen Standort: Bist du mehr als 100 m vom Lokal entfernt, bekommst du einen Hinweis – eintragen kannst du trotzdem.

Gibt es eine Sorte in einem Lokal nicht (mehr), kannst du das im selben Fenster melden.

## Mein Standort

Mit dem Standort-Button (◎) unten links auf der Karte springst du zu deiner aktuellen Position.

---

# FAQ

**Wieso ist mein lieblings Lokal nicht auf der Karte?**

> Die Lokale werden einmal am Tag von OpenStreetMap abgerufen. Nur wenn ein Lokal dort hinterlegt ist, kann es in der Spritzmap vorkommen. 

**Welche KI wird für die Fotoanalyse benutzt?**

> Die Glasform erkennt **COCO-SSD**, ein frei verfügbares, vortrainiertes Modell zur Objekterkennung (MobileNet-Variante, trainiert auf dem öffentlichen COCO-Bilddatensatz). Es findet im Foto ein „Weinglas" oder einen „Becher" und markiert, wo das Glas im Bild steht.
> Das Mischverhältnis ist keine KI im engeren Sinn: Aus dem Bereich des Glases, in dem das Getränk steht, werden die Farbwerte der Pixel gemessen und mit der Farbe der gewählten Sorte verglichen.
> Beides läuft **komplett in deinem Browser** (mit TensorFlow.js). Das Modell (ca. 5 MB) liegt auf unserem eigenen Server und wird beim ersten Foto einmalig geladen. Dein Foto wird für die Analyse **nicht** an einen KI-Dienst geschickt – hochgeladen wird es erst beim Speichern, und nur, damit es im Popup erscheint.

**Warum fragt die SpritzMap beim Eintragen nach meinem Standort?**

> Damit die Karte verlässlich bleibt: Das Mischverhältnis lässt sich im Nachhinein kaum noch einschätzen. Die Entfernung zum Lokal wird nur in deinem Browser berechnet und nicht gespeichert. Gibst du deinen Standort nicht frei, kannst du ganz normal weiter eintragen.

**Wie berechnet sich die Einfärbung der Gebiete?**

> Die Intensität ergibt sich aus zwei Faktoren: dem **Preis** und dem **Mischverhältnis** der erfassten Einträge im jeweiligen Gebiet.
> Zuerst wird ein Preis-Score berechnet: Günstige Gebiete bekommen einen hohen Wert (nahe 1), teure einen niedrigen (nahe 0). Der Vergleich erfolgt logarithmisch – ein Unterschied von 5 € auf 6 € fällt stärker ins Gewicht als von 9 € auf 10 €. Anschließend wird dieser Wert mit dem durchschnittlichen Mischverhältnis der Einträge multipliziert – ein kräftiges Mischverhältnis verstärkt die Einfärbung, ein mildes schwächt sie ab. Das Ergebnis ist der **Spritz-Index** (0–100), der direkt die Deckkraft der Gebietsfarbe bestimmt.
