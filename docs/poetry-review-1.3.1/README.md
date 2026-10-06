# Poetry re-render review (versed-pdf 1.3.1)

Every OpenITI source among the Archive receipts with `%~%` or `# % … %` verse
lines (28 of 740) was re-rendered with this branch through the archive gate
(`archive_openiti_pdf_pass.py` `render_one`, text layer kept, scholarly theme)
into a scratch outbox, with Amiri 1.003 installed. Pango resolves "Amiri" and
the PDFs embed `Amiri-Regular`. All 28 pass the gate.

Columns: verse pairs/misread (empty or numeric hemistich) for the parser C1's
outbox was rendered with (pre-1.3.0 `main`) → this branch; "text layer" =
words on the middle reviewed page whose letters occur in the source (running
headers, verse numbers and page numbers account for the rest). Pages were
reviewed at 150 dpi for hemistich order, verse numbers in the margin,
clipping and the Amiri face.

No poetry item on the Archive has a PDF yet, so nothing published needs
replacing. Every PDF already in C1's outbox was set without Amiri (fontconfig
fell back to AlNile / DecoType Naskh) and should be re-rendered with 1.3.1
before it is published.

| book | pages | pages reviewed | pairs/misread old → new | text layer Poppler | text layer MuPDF | C1 outbox | verdict | notes | sheet |
|---|---|---|---|---|---|---|---|---|---|
| 0466IbnSinanKhafaji.Diwan | 117 | 3, 60, 117 | 2432/2285 → 2417/0 | 208/208 | 168/188 | not rendered yet | **pass** | Old parser misread 2285/2432 pairs; now 0. Verse numbers in margin, meter headings centred. | [sheet](0466IbnSinanKhafaji.Diwan.sheet.jpg) |
| 0481AnsariHarawi.ManazilSairin | 65 | 3, 34, 65 | 12/0 → 12/0 | 186/188 | 186/188 | not rendered yet | **pass** | Pairs, order and margins checked; no issues. | [sheet](0481AnsariHarawi.ManazilSairin.sheet.jpg) |
| 0500AbuNasrMaqdisi.LataifWaZaraif | 180 | 3, 92, 180 | 1087/0 → 1087/0 | 200/203 | 190/198 | not rendered yet | **pass*** | Couplets fine; first heading/header reads "PARATEXT" (source markup). | [sheet](0500AbuNasrMaqdisi.LataifWaZaraif.sheet.jpg) |
| 0500Anonymous.AwtanWaBuldan | 27 | 3, 15, 27 | 4/0 → 4/0 | 232/235 | 234/236 | not rendered yet | **pass** | Pairs, order and margins checked; no issues. | [sheet](0500Anonymous.AwtanWaBuldan.sheet.jpg) |
| 0533IbnKhafajaShacir.Diwan | 41 | 3, 22, 41 | 752/646 → 746/0 | 201/201 | 177/189 | not rendered yet | **pass** | Old parser misread 646/752 pairs; now 0. | [sheet](0533IbnKhafajaShacir.Diwan.sheet.jpg) |
| 0544IbnAmin.Istidrak | 71 | 3, 37, 71 | 6/0 → 6/0 | 141/146 | 129/140 | not rendered yet | **source issue** | Source carries "![image filename](…png)" lines; running header shows the URI. | [sheet](0544IbnAmin.Istidrak.sheet.jpg) |
| 0567CarqalaKalbi.Diwan | 51 | 3, 27, 51 | 899/734 → 894/0 | 153/157 | 123/142 | not rendered yet | **pass** | Old parser misread 734/899 pairs; now 0. | [sheet](0567CarqalaKalbi.Diwan.sheet.jpg) |
| 0650IbnMuhammadRadiDinSaghani.Mawducat | 14 | 3, 9, 14 | 3/0 → 3/0 | 169/176 | 169/176 | rendered (old code, AlNile font) | **pass** | 3 verse lines re-paired; C1 outbox copy has the old layout. | [sheet](0650IbnMuhammadRadiDinSaghani.Mawducat.sheet.jpg) |
| 0671AbuCabdAllahQurtubi.Asna | 442 | 3, 223, 442 | 174/13 → 170/0 | 272/272 | 272/272 | not rendered yet | **source issue** | Prose with OCR noise: %~% margin junk now kept as verse lines (no fake couplets); source carries "![image filename](…png)" lines and no catalog title (running header shows the URI). | [sheet](0671AbuCabdAllahQurtubi.Asna.sheet.jpg) |
| 0688ShabZarif.Diwan | 132 | 3, 68, 132 | 2449/2026 → 2424/0 | 173/178 | 143/161 | not rendered yet | **pass** | Old parser misread 2026/2449 pairs; now 0. Diacritized source renders cleanly. | [sheet](0688ShabZarif.Diwan.sheet.jpg) |
| 0711IbnIbrahimCimadDinWasiti.Tadhkira | 21 | 3, 12, 21 | 2/0 → 2/0 | 218/220 | 216/219 | rendered (old code, AlNile font) | **pass** | 47 words after "PageV01P023" were lost by the old parser; restored. | [sheet](0711IbnIbrahimCimadDinWasiti.Tadhkira.sheet.jpg) |
| 0717CalaDinIbnCabdZahir.RawdZahir | 21 | 3, 12, 21 | 11/0 → 11/0 | 266/269 | 266/269 | not rendered yet | **pass** | Pairs, order and margins checked; no issues. | [sheet](0717CalaDinIbnCabdZahir.RawdZahir.sheet.jpg) |
| 0725BaybarsMansuri.MawacizAbrar | 27 | 3, 15, 27 | 5/0 → 5/0 | 231/232 | 231/232 | not rendered yet | **pass** | Pairs, order and margins checked; no issues. | [sheet](0725BaybarsMansuri.MawacizAbrar.sheet.jpg) |
| 0730ShaficIbnCali.HusnManaqib | 136 | 3, 70, 136 | 233/0 → 233/0 | 251/253 | 251/253 | not rendered yet | **pass** | Pairs, order and margins checked; no issues. | [sheet](0730ShaficIbnCali.HusnManaqib.sheet.jpg) |
| 0748Dhahabi.RuwatThiqat | 14 | 3, 9, 14 | 1/0 → 1/0 | 241/251 | 241/254 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0748Dhahabi.RuwatThiqat.sheet.jpg) |
| 0748Dhahabi.TarjamatImamShaybani | 12 | 3, 8, 12 | 7/0 → 7/0 | 245/248 | 245/248 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0748Dhahabi.TarjamatImamShaybani.sheet.jpg) |
| 0776JamalDinSurramarri.Hamiyya | 11 | 3, 7, 11 | 152/0 → 152/0 | 194/199 | 194/199 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0776JamalDinSurramarri.Hamiyya.sheet.jpg) |
| 0795IbnRajabHanbali.KalimatIkhsas | 24 | 3, 14, 24 | 2/0 → 14/0 | 220/223 | 220/223 | not rendered yet | **pass** | 14 pairs (old: 2); stray "$" markers removed. | [sheet](0795IbnRajabHanbali.KalimatIkhsas.sheet.jpg) |
| 0833IbnJazari.DurraMudiyya | 16 | 3, 10, 16 | 10/0 → 182/0 | 238/238 | 203/220 | refused | **pass** | 182 pairs (old parser found 10); inline "$" title now a heading. | [sheet](0833IbnJazari.DurraMudiyya.sheet.jpg) |
| 0852IbnHajarCasqalani.AmaliHalabiyya | 15 | 3, 9, 15 | 0/0 → 2/0 | 290/293 | 290/293 | rendered (old code, AlNile font) | **pass** | 2 verse pairs now recognised; C1 outbox copy has the old layout. | [sheet](0852IbnHajarCasqalani.AmaliHalabiyya.sheet.jpg) |
| 0875Jizi.Tadhkira | 6 | 3, 5, 6 | 4/0 → 4/0 | 214/221 | 214/221 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0875Jizi.Tadhkira.sheet.jpg) |
| 0919IbnGhaziMiknasi.TacallulBiRusumIsnad | 18 | 3, 11, 18 | 1/0 → 1/0 | 298/299 | 298/299 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0919IbnGhaziMiknasi.TacallulBiRusumIsnad.sheet.jpg) |
| 0921JibrailIbnQilaci.MadihaCalaJabalLubnan | 28 | 3, 16, 28 | 587/0 → 587/0 | 191/193 | 145/170 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0921JibrailIbnQilaci.MadihaCalaJabalLubnan.sheet.jpg) |
| 0921JibrailIbnQilaci.QissatMarNuhra | 12 | 3, 8, 12 | 226/0 → 226/0 | 186/186 | 140/163 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](0921JibrailIbnQilaci.QissatMarNuhra.sheet.jpg) |
| 1055AhmadSharafi.Manzuma | 4 | 3, 4 | 31/0 → 31/0 | 130/130 | 104/117 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](1055AhmadSharafi.Manzuma.sheet.jpg) |
| 1280MullaCimranFarisi.Qasida | 12 | 3, 8, 12 | 116/24 → 110/0 | 128/130 | 118/125 | refused | **pass** | Takhmis: pairs and single lines interleave in source order (old: 24/116 misread, refused). | [sheet](1280MullaCimranFarisi.Qasida.sheet.jpg) |
| 1306YusufBeyKaram.ZajaliyyatDawudBasha | 4 | 3, 4 | 27/0 → 27/0 | 91/91 | 75/83 | rendered (old code, AlNile font) | **pass** | Pairs, order and margins checked; no issues. | [sheet](1306YusufBeyKaram.ZajaliyyatDawudBasha.sheet.jpg) |
| 1357IstifanThani.ZajaliyyatHarb | 14 | 3, 9, 14 | 245/1 → 244/0 | 143/144 | 113/129 | rendered (old code, AlNile font) | **pass*** | Zajal pairs fine; folio anchors fixed (a verse was lost); running header shows the URI (no catalog title). | [sheet](1357IstifanThani.ZajaliyyatHarb.sheet.jpg) |
