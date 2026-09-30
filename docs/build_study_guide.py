"""Build docs/Phase2_Study_Guide.pdf -- the team's revision + presentation handbook.

    ./venv/Scripts/python.exe docs/build_study_guide.py

Plain ReportLab (no LaTeX needed). Keep every glyph ASCII: the built-in fonts
have no rupee sign, so we write "Rs." throughout.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                ListFlowable, ListItem, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
OUT = HERE / "Phase2_Study_Guide.pdf"

INK = colors.HexColor("#1a1a1a")
ACCENT = colors.HexColor("#1f4e79")
ACCENT2 = colors.HexColor("#0f7b6c")
WARN = colors.HexColor("#9c2b2b")
LIGHT = colors.HexColor("#f2f5f8")
BOXBG = colors.HexColor("#eef4fa")
WHYBG = colors.HexColor("#eaf6f2")
ASKBG = colors.HexColor("#fdf3e7")
RULE = colors.HexColor("#c9d4e0")

ss = getSampleStyleSheet()


def style(name, **kw):
    base = kw.pop("parent", ss["BodyText"])
    return ParagraphStyle(name, parent=base, **kw)


S = {
    "title": style("t", parent=ss["Title"], fontSize=24, leading=29,
                   textColor=ACCENT, spaceAfter=6),
    "subtitle": style("st", fontSize=12.5, leading=17, textColor=INK,
                      alignment=TA_CENTER, spaceAfter=4),
    "h1": style("h1", parent=ss["Heading1"], fontSize=16.5, leading=20,
                textColor=ACCENT, spaceBefore=16, spaceAfter=7),
    "h2": style("h2", parent=ss["Heading2"], fontSize=12.5, leading=16,
                textColor=INK, spaceBefore=11, spaceAfter=4),
    "p": style("p", fontSize=10.2, leading=14.6, textColor=INK,
               alignment=TA_JUSTIFY, spaceAfter=6),
    "bul": style("bul", fontSize=10.2, leading=14.2, textColor=INK,
                 spaceAfter=2),
    "small": style("sm", fontSize=8.8, leading=12, textColor=colors.HexColor("#555")),
    "cap": style("cap", fontSize=8.6, leading=11.5, alignment=TA_CENTER,
                 textColor=colors.HexColor("#555"), spaceBefore=3),
    "boxh": style("bh", fontSize=10, leading=13, textColor=ACCENT,
                  fontName="Helvetica-Bold", spaceAfter=3),
    "boxp": style("bp", fontSize=9.7, leading=13.6, textColor=INK,
                  alignment=TA_JUSTIFY),
    "cell": style("cl", fontSize=8.9, leading=11.8, textColor=INK),
    "cellb": style("clb", fontSize=8.9, leading=11.8, textColor=INK,
                   fontName="Helvetica-Bold"),
    "q": style("q", fontSize=10.2, leading=13.8, textColor=ACCENT,
               fontName="Helvetica-Bold", spaceBefore=7, spaceAfter=2),
    "a": style("a", fontSize=10.0, leading=14.0, textColor=INK,
               alignment=TA_JUSTIFY, spaceAfter=3),
}


# ---------------------------------------------------------------- helpers ---
def P(text, s="p"):
    return Paragraph(text, S[s])


def H1(text):
    return Paragraph(text, S["h1"])


def H2(text):
    return Paragraph(text, S["h2"])


def BULLETS(items, s="bul"):
    return ListFlowable(
        [ListItem(Paragraph(i, S[s]), leftIndent=14, value="bullet")
         for i in items],
        bulletType="bullet", start="square", leftIndent=12,
        bulletFontSize=6, bulletColor=ACCENT, spaceAfter=6)


def NUMBERED(items):
    return ListFlowable(
        [ListItem(Paragraph(i, S["bul"]), leftIndent=16) for i in items],
        bulletType="1", leftIndent=14, spaceAfter=6)


def BOX(title, body, kind="why"):
    bg = {"why": WHYBG, "note": BOXBG, "ask": ASKBG}[kind]
    edge = {"why": ACCENT2, "note": ACCENT, "ask": colors.HexColor("#b8730f")}[kind]
    inner = [Paragraph(title, ParagraphStyle("bh2", parent=S["boxh"],
                                             textColor=edge))]
    for para in body:
        inner.append(Paragraph(para, S["boxp"]))
        inner.append(Spacer(1, 3))
    t = Table([[inner]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.6, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


def TABLE(rows, widths, header=True, align_right=()):
    data = []
    for r_i, row in enumerate(rows):
        line = []
        for c_i, cell in enumerate(row):
            st = "cellb" if (header and r_i == 0) else "cell"
            line.append(Paragraph(str(cell), S[st]))
        data.append(line)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    for c in align_right:
        cmds.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(cmds))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 9)])


def FIG(relpath, caption, width=150 * mm):
    path = HERE / relpath
    if not path.exists():
        return P("[missing figure: %s]" % relpath, "small")
    img = Image(str(path))
    ratio = img.imageHeight / float(img.imageWidth)
    img.drawWidth = width
    img.drawHeight = width * ratio
    return KeepTogether([Spacer(1, 4), img, Paragraph(caption, S["cap"]),
                         Spacer(1, 8)])


def QA(q, a):
    return KeepTogether([Paragraph(q, S["q"]), Paragraph(a, S["a"])])


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(22 * mm, 285 * mm, 188 * mm, 285 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#777"))
    canvas.drawString(22 * mm, 287 * mm,
                      "NSE AI Options Bot - Phase 2 Study Guide")
    canvas.drawRightString(188 * mm, 287 * mm, "Team revision handbook")
    canvas.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canvas.drawCentredString(105 * mm, 11 * mm, "Page %d" % doc.page)
    canvas.restoreState()


# ------------------------------------------------------------------ story ---
story = []
A = story.append

# ---- cover
A(Spacer(1, 38 * mm))
A(Paragraph("Phase 2 Study Guide", S["title"]))
A(Paragraph("AI Options Trading Bot - NSE BankNifty", S["subtitle"]))
A(Spacer(1, 4))
A(Paragraph("Everything we built after Phase 1, in plain language:<br/>"
            "what we did, why we did it, and how to defend it in a viva.",
            S["subtitle"]))
A(Spacer(1, 14))
A(TABLE([["Team", "Anubhaw Raj, Subham Singh, Harsh Raj Sharma, Nirban Das"],
         ["Companion documents",
          "Phase 1 theory paper (May 2026); Phase 2 theory paper "
          "(docs/phase2_report.tex)"],
         ["Code", "github.com/anubhaw0raj/nse_ai_options_bot"],
         ["Data", "1-minute BankNifty option chain, spot and futures, "
                  "2020 to 2024 (about 1,200 trading days)"],
         ["Status", "Phases 0 to 4 complete. Strategy is NOT profitable yet - "
                    "and that is a finding, not a failure."]],
        widths=[38 * mm, 127 * mm], header=False))
A(BOX("How to use this guide",
      ["Read sections 1 to 3 to get the story. Sections 4 to 9 are the "
       "technical core - one page per idea, always in the order "
       "<b>what / why / how it helps</b>. Section 11 is a question bank for "
       "the presentation. Section 12 is the one-page number sheet to "
       "memorise the night before.",
       "If you only have twenty minutes: read section 1, the numbers sheet "
       "in section 12, and the five questions marked HIGH RISK in "
       "section 11."], "note"))
A(PageBreak())

# ---- 1 summary
A(H1("1. The sixty-second summary"))
A(P("We are building a trading system that looks at BankNifty option prices "
    "every minute, predicts whether an option's price will go up over the "
    "next few minutes, and buys or sells accordingly. Phase 1 proved the idea "
    "could work on a single day. Phase 2 turned that demo into a proper "
    "measuring instrument and then measured it honestly over entire years."))
A(P("<b>The one-line result:</b> after fixing a data bug, adding real trading "
    "costs and testing on a full year instead of one day, our yearly loss "
    "dropped from about Rs. 3.5 lakh to about Rs. 10,000 - a 35 times "
    "improvement - but the strategy still does not make money."))
A(BOX("Why a negative result is still a good result",
      ["Before Phase 2 the system reported profits that did not exist, "
       "because it ignored brokerage and taxes and tested on one lucky day. "
       "Now every number we report is after all charges, on data the model "
       "had never seen. We can trust our own measurements. That is the "
       "difference between a college demo and a research system.",
       "SEBI's own study found 93 percent of individual traders in this "
       "market lose money. Any project claiming easy profits here should be "
       "assumed wrong until proven otherwise."]))
A(H2("The three sentences that carry the whole project"))
A(NUMBERED([
    "<b>The signal is weak.</b> Before costs, the model makes roughly zero "
    "money per trade at a 5-minute horizon, and a small positive amount at a "
    "15-minute horizon.",
    "<b>The costs are large.</b> Every completed trade costs about Rs. 57, "
    "of which Rs. 40 is flat brokerage that does not shrink with trade size.",
    "<b>So the fix is not a bigger model, it is a bigger edge per trade.</b> "
    "Trade less often, hold a little longer, and make each trade count."]))
A(PageBreak())

# ---- 2 vocabulary
A(H1("2. Vocabulary - the words we must not fumble"))
A(P("If a panel member asks a definition and we stumble, everything after "
    "that sounds shaky. These are the only terms we actually need."))
A(TABLE([
    ["Term", "Plain meaning", "Everyday comparison"],
    ["Option (CE / PE)",
     "A contract that gives the right, not the duty, to buy (CE = call) or "
     "sell (PE = put) BankNifty at a fixed price before a fixed date.",
     "A token that locks today's price for later."],
    ["Premium",
     "The price of the option itself. This is what we buy and sell.",
     "The cost of the token, not the cost of the index."],
    ["Strike",
     "The fixed price written into the contract.",
     "The price printed on the token."],
    ["ATM (at the money)",
     "The strike closest to where BankNifty is trading right now. We only "
     "trade ATM contracts because they are the most liquid.",
     "The most popular item on the menu - always in stock."],
    ["Lot size",
     "Options trade in fixed bundles. BankNifty was 20 per lot in 2020, "
     "25 later, then 15, then 30. Profit multiplies by this number.",
     "Eggs sold only by the dozen."],
    ["Expiry",
     "The date the contract dies. BankNifty has weekly expiries.",
     "The last date printed on a movie ticket."],
    ["Implied volatility (IV)",
     "How much movement the market is currently pricing in. High IV means "
     "expensive options.",
     "Surge pricing on a cab app."],
    ["Delta",
     "How much the option price moves when BankNifty moves by one point. "
     "ATM options have delta near 0.5.",
     "Gear ratio between the index and our position."],
    ["Theta",
     "How much value the option loses every day just from time passing. "
     "Always works against a buyer.",
     "Ice melting - you lose even when nothing happens."],
    ["Open interest (OI)",
     "How many contracts are currently open in the market. Rising OI means "
     "new money is entering that strike.",
     "How many people are still holding tickets, not how many tickets were "
     "resold."],
    ["Walk-forward test",
     "Train on the past 10 days, test on day 11, slide forward, repeat for a "
     "whole year.",
     "Studying last week's lectures, then sitting an unseen test today."],
    ["Calibration",
     "Making the model's confidence honest, so that 'I am 70 percent sure' "
     "is right about 70 percent of the time.",
     "A weather app whose '70 percent rain' days actually rain 7 times "
     "out of 10."],
], widths=[28 * mm, 82 * mm, 55 * mm]))
A(PageBreak())

# ---- 3 story
A(H1("3. Where Phase 1 left us"))
A(P("Phase 1 (submitted in the 6th semester) built the pipeline: read the raw "
    "CSV files, compute option maths (IV and the Greeks), train a Gradient "
    "Boosting classifier to predict 'will this option be higher in 5 "
    "minutes', and run a small state machine that holds at most one position "
    "at a time."))
A(H2("What Phase 1 got right"))
A(BULLETS([
    "<b>Classification, not regression.</b> Predicting the exact future price "
    "failed, because options lose value with time, so the model just learned "
    "to predict 'down' forever. Asking a yes/no question fixed that.",
    "<b>One position at a time.</b> An earlier version traded every strike at "
    "once and reported Rs. 5.58 crore of fake profit. Restricting to a single "
    "ATM contract made the simulation realistic.",
    "<b>Momentum instead of raw prices.</b> The model was memorising price "
    "levels (the raw price had 84.8 percent importance). Replacing prices "
    "with percentage changes forced it to learn patterns instead.",
]))
A(H2("What Phase 1 could not tell us"))
A(BULLETS([
    "Was the training label even correct? (It was not - section 4.)",
    "Would the profit survive brokerage and taxes? (It did not - section 5.)",
    "Would it work on days other than 10 January 2020? (One day proves "
    "nothing.)",
    "Did '74 percent accuracy' mean anything in rupees? (Accuracy and profit "
    "are different things - section 7.)",
]))
A(BOX("The sentence to use if asked 'so was Phase 1 wrong?'",
      ["Phase 1 was a correct proof of concept and an honest one - it "
       "published its own flaws, like the 84.8 percent price-importance "
       "problem. Phase 2 did not replace it; it asked the harder questions "
       "that only appear once you test at scale.", ]))
A(PageBreak())

# ---- 4 label bug
A(H1("4. The bug that quietly inflated our accuracy"))
A(H2("What we found"))
A(P("To train the model we must label each row: did the price go UP or not? "
    "Phase 1 built that label by taking the price 5 rows further down the "
    "table. But the table holds hundreds of different contracts stacked "
    "together and sorted by time. So the row '5 later' usually belongs to a "
    "<b>different option</b>."))
A(TABLE([
    ["Row", "Time", "Contract", "Price", "What the old code compared"],
    ["1", "09:20", "32200 CE", "300", "compares with row 6 below"],
    ["2", "09:20", "32300 CE", "250", ""],
    ["3", "09:20", "32200 PE", "180", ""],
    ["4", "09:21", "32200 CE", "302", ""],
    ["5", "09:21", "32300 CE", "251", ""],
    ["6", "09:21", "32200 PE", "179", "<b>WRONG</b> - a PUT's price used as "
                                      "the CALL's future"],
], widths=[12 * mm, 18 * mm, 26 * mm, 18 * mm, 91 * mm]))
A(H2("Why it survived Phase 1 testing"))
A(P("Because it still produced high accuracy. Comparing a call with a put is "
    "easy to predict from the strike alone, so the model scored well on a "
    "meaningless question. <b>High accuracy on the wrong question is the most "
    "dangerous failure in machine learning for finance.</b>"))
A(H2("How we fixed it"))
A(BULLETS([
    "<b>Group by contract first,</b> then look forward in time. Now the "
    "future price of 32200 CE can only come from 32200 CE.",
    "<b>Time-gap guard.</b> Some contracts do not trade every minute. If the "
    "next available quote is 40 minutes later, we throw that label away "
    "instead of pretending it was 5 minutes.",
    "<b>Deadband.</b> A one-paisa flicker used to count as UP. Now the price "
    "must rise by at least a set percentage to count, so the model learns "
    "real moves, not noise.",
    "<b>A unit test proves it.</b> We built a fake dataset with two "
    "contracts moving in opposite directions; the test fails with the old "
    "code and passes with the new one.",
]))
A(BOX("Why this matters for the project",
      ["Everything downstream - accuracy, probability, profit - was built on "
       "this label. Fixing it means our numbers now describe a question we "
       "can actually trade on. It is also the single best example we have of "
       "doing real engineering rather than just calling library functions."]))
A(PageBreak())

# ---- 5 costs
A(H1("5. Costs - the part that decides everything"))
A(P("Phase 1 computed profit as (exit price - entry price) x lot size. Real "
    "trading has six statutory charges plus slippage. When we added them, the "
    "picture inverted."))
A(H2("One round trip on a Rs. 300 option, lot size 20 (position Rs. 6,000)"))
A(TABLE([
    ["Charge", "Rate", "Amount", "Note"],
    ["Brokerage", "Rs. 20 per order, flat", "Rs. 40.00",
     "Same whether we trade 1 lot or 5 - this is the killer"],
    ["STT", "0.0625 percent of sell premium", "Rs. 3.75", "Only on exit"],
    ["Exchange charge", "0.05 percent of turnover", "Rs. 6.00", "Both sides"],
    ["SEBI fee", "Rs. 10 per crore", "Rs. 0.01", "Negligible"],
    ["Stamp duty", "0.003 percent on buy", "Rs. 0.18", "Entry only"],
    ["GST", "18 percent on the fees", "Rs. 8.28", "Tax on the tax"],
    ["<b>Total</b>", "", "<b>Rs. 58.22</b>", "That is 0.97 percent of the "
                                            "position"],
    ["Slippage", "0.25 percent per side", "0.50 percent",
     "We never get the exact screen price"],
    ["<b>Break-even move</b>", "", "<b>about 1.5 percent</b>",
     "The option must rise this much before we earn one rupee"],
], widths=[30 * mm, 42 * mm, 28 * mm, 65 * mm]))
A(BOX("Real-life comparison",
      ["It is a toll booth. Every trade pays the toll in both directions "
       "whether the journey was useful or not. If you take twenty short trips "
       "a day you pay twenty tolls; the trips have to be long enough to be "
       "worth it. That single idea explains almost every design decision in "
       "Phase 2."]))
A(H2("The consequences we acted on"))
A(TABLE([
    ["Because...", "We changed..."],
    ["Cheap options have a huge percentage cost (a Rs. 100 option needs a 3 "
     "percent move)", "We should raise the minimum premium we are willing to "
     "trade (planned)"],
    ["The toll is per trade, not per rupee",
     "We cut trading from about 20 times a day to a few times a week"],
    ["A longer horizon gives a bigger expected move for the same toll",
     "We tested 5, 15 and 30 minutes - 15 won"],
    ["Flat brokerage is amortised over bigger positions",
     "We built conviction-based sizing - but see section 8 for why we turned "
     "it off"],
], widths=[85 * mm, 80 * mm]))
A(PageBreak())

# ---- 6 features and store
A(H1("6. What the model looks at, and how we made it fast"))
A(H2("The feature store"))
A(P("Computing IV and the Greeks for millions of rows is slow. We now compute "
    "each trading day once and save it as a Parquet file (a compressed, "
    "column-wise format). About 1,200 days were built at roughly 0.8 seconds "
    "per day. After that, a full-year experiment takes minutes instead of "
    "hours - which is what made all the experiments in section 9 possible."))
A(BOX("Real-life comparison",
      ["Meal prep. Cooking each meal from scratch takes an hour; prepping "
       "once on Sunday means every weekday meal takes five minutes. Same "
       "food, one-tenth of the effort."], "note"))
A(H2("The four new families of inputs (Phase 1 had only the first row)"))
A(TABLE([
    ["Family", "Features", "Why it should help"],
    ["Contract state (Phase 1)",
     "moneyness, time to expiry, IV, delta, gamma, theta, vega",
     "Describes what the contract is worth and how it reacts"],
    ["Contract flow",
     "OI change 1m/5m, volume z-score, IV z-score",
     "Shows whether new money is entering this exact strike, and whether "
     "today's activity is unusual for it"],
    ["Whole-chain sentiment",
     "put/call ratio (OI and volume), IV skew",
     "Shows which way the entire option chain is leaning"],
    ["Futures positioning",
     "basis, futures returns, futures OI, distance from VWAP",
     "Big players trade futures first; futures often lead the options"],
    ["Regime and clock",
     "realised volatility 15m/60m, minutes since open, time-of-day as "
     "sine/cosine, day of week",
     "A quiet market and a panicking market need different behaviour; "
     "expiry day behaves differently from Monday"],
], widths=[32 * mm, 58 * mm, 75 * mm]))
A(H2("Two small ideas worth explaining in the viva"))
A(BULLETS([
    "<b>Z-scores instead of raw numbers.</b> Volume of 50,000 means nothing "
    "by itself. Volume three standard deviations above this contract's own "
    "recent average means something. This is the Phase 1 lesson about "
    "absolute prices, applied to every input.",
    "<b>Time as a circle.</b> If we feed the clock as a plain number, the "
    "model thinks 09:15 and 15:30 are far apart. Both are actually volatile "
    "session edges. So we encode time as sine and cosine, which wraps it "
    "around a circle.",
]))
A(PageBreak())

# ---- 7 model + decisions
A(H1("7. The model, its confidence, and when we refuse to trade"))
A(H2("Why LightGBM"))
A(P("We moved from scikit-learn's gradient boosting to LightGBM because we "
    "retrain the model for every single test day - over a thousand times per "
    "experiment. LightGBM buckets the numbers into bins, grows trees "
    "leaf-by-leaf instead of level-by-level, and handles missing values "
    "natively (our rolling features are undefined in the first minutes of "
    "each session). It is up to 20 times faster at similar accuracy."))
A(H2("Calibration: making confidence honest"))
A(P("A boosted model's '0.70' is not really 70 percent - these models push "
    "scores towards the extremes. That matters for us more than for a normal "
    "classifier, because every decision we make is a threshold on that "
    "number. So we fit an <b>isotonic regression</b> on two recent days that "
    "the model was not trained on: it learns a staircase-shaped correction "
    "that maps raw scores to honest probabilities."))
A(BOX("Real-life comparison",
      ["A student who says 'I am 90 percent sure' but is right only half the "
       "time is not useless - their ranking of questions may still be "
       "correct. You just have to learn the translation: when they say 90, "
       "read 50. Isotonic regression learns exactly that translation table.",
       "Important detail for a viva: calibration never changes the ORDER of "
       "predictions, so it cannot change AUC. It only changes what the number "
       "means."]))
A(H2("Choosing the entry threshold by money, not by accuracy"))
A(P("Accuracy puts the cut-off at 0.5. That is only correct when wins and "
    "losses are equal in size and trading is free - neither is true. So we "
    "try each candidate threshold (0.65, 0.70, 0.75, 0.80) on the two "
    "calibration days, simulate the trades with full costs, and pick the "
    "threshold that made the most money. Ties go to the higher threshold, "
    "because fewer trades means less cost and less risk."))
A(H2("The skip rule - the most under-rated part of the system"))
A(P("If even the best threshold loses money on those two recent days, we do "
    "not trade the next day at all. In the final configuration this means we "
    "sit out about 71 percent of days (173 out of 242 in 2020)."))
A(BOX("Real-life comparison",
      ["A good poker player folds most hands. Folding is not inactivity, it "
       "is a decision with positive value, because playing costs money. Our "
       "system folds whenever it cannot demonstrate an edge."]))
A(PageBreak())

# ---- 8 risk
A(H1("8. Risk management, and two lessons that cost us real money"))
A(H2("What the risk layer does"))
A(BULLETS([
    "<b>Entry gates:</b> at most 4 trades a day per contract; stop for the "
    "day after Rs. 3,000 of losses; no entries in the first 5 minutes or "
    "after 15:00; no entries when volatility is too low (nothing to catch) or "
    "too high (spreads explode).",
    "<b>Sizing:</b> more lots when the model is more confident, capped by a "
    "maximum premium outlay.",
    "<b>Exits:</b> stop-loss, take-profit, signal reversal, time limit, "
    "end of day - whichever comes first.",
]))
A(H2("Lesson 1: a tight stop-loss lost us about Rs. 1.16 lakh"))
A(P("We first used a 12 percent stop-loss. It was the worst decision in the "
    "project. Look at the profit split by exit reason: <b>every other exit "
    "type made money in both years, and the stop-loss alone lost Rs. 64,738 "
    "in 2020 and Rs. 51,164 in 2021.</b>"))
A(TABLE([
    ["Exit reason", "2020 count", "2020 total", "2021 count", "2021 total"],
    ["Signal reversal", "55", "+Rs. 8,083", "90", "+Rs. 23,067"],
    ["Target hit", "10", "+Rs. 15,863", "8", "+Rs. 11,319"],
    ["Time limit", "12", "+Rs. 1,389", "19", "-Rs. 85"],
    ["<b>Stop-loss</b>", "<b>65</b>", "<b>-Rs. 64,738</b>", "<b>50</b>",
     "<b>-Rs. 51,164</b>"],
], widths=[38 * mm, 28 * mm, 33 * mm, 28 * mm, 38 * mm]))
A(P("<b>Why it happened.</b> An ATM option with delta near 0.5 moves about 12 "
    "percent when BankNifty moves only 0.1 to 0.2 percent - which happens "
    "many times an hour. Worse, a 1-minute bar's low is partly just the bid "
    "side of the bid-ask bounce, not a real price move. This is Roll's 1984 "
    "result: observed prices bounce between bid and ask even when the true "
    "value has not moved. So our stop was being triggered by noise, and each "
    "trigger cost a full round trip of charges."))
A(BOX("Real-life comparison",
      ["A smoke alarm so sensitive that it goes off every time you make "
       "toast. You do not get safety, you get 65 false alarms and a lot of "
       "wasted trips. We widened the stop to 30 percent so it is genuine "
       "disaster insurance, and stop-outs fell from 65 to 10."]))
A(H2("Lesson 2: bigger position sizes made losses bigger, not smaller"))
A(P("The idea was reasonable: the Rs. 40 brokerage is the same for 1 lot or "
    "3, so bigger positions dilute it. But the 2-lot bucket was the worst "
    "performer in three of four runs (for example -Rs. 20,789 in 2021 versus "
    "-Rs. 2,595 for 1 lot). The maths is simple: if the average trade has "
    "negative expectancy, multiplying the size multiplies the loss. Sizing "
    "amplifies an edge; it cannot create one."))
A(BOX("The rule we adopted",
      ["<i>Earn the right to size up.</i> Keep max_lots = 1 until walk-forward "
       "expectancy is positive. This is a sentence worth saying out loud in "
       "the presentation - it shows discipline."]))
A(PageBreak())

# ---- 9 results
A(H1("9. Results - the numbers and how to read them"))
A(H2("The progression on the same year of data (2020)"))
A(TABLE([
    ["Stage", "What changed", "Trades", "Net result", "Improvement"],
    ["Phase 2 baseline", "Real costs, correct labels, full year", "4,706",
     "-Rs. 349,791", "starting point"],
    ["+ calibration, auto threshold, skip rule", "5-minute horizon", "470",
     "-Rs. 22,250", "15.7 times better"],
    ["+ 15-minute horizon", "hold a bit longer", "276", "-Rs. 9,983",
     "<b>35 times better</b>"],
    ["+ risk layer (final)", "30 percent stop, 1 lot", "97", "-Rs. 12,311",
     "28 times better"],
], widths=[38 * mm, 42 * mm, 18 * mm, 30 * mm, 37 * mm]))
A(FIG("figures/fig01_baseline_equity.png",
      "The baseline: a smooth downhill slide. That shape means costs, not bad "
      "predictions - the losses accrue with trade count."))
A(FIG("figures/fig02_h15_equity.png",
      "The best configuration: far fewer trades, flat stretches where the "
      "system refused to trade, and a loss 35 times smaller."))
A(H2("What each metric means when they ask"))
A(TABLE([
    ["Metric", "Plain meaning", "Ours"],
    ["Gross P&L", "Profit before charges - the raw skill of the model",
     "+Rs. 5,710 at 15 minutes (slightly positive)"],
    ["Net P&L", "What actually lands in the account", "-Rs. 9,983"],
    ["Expectancy per trade", "Average rupees made or lost per trade",
     "-Rs. 36.2"],
    ["Profit factor", "Total wins divided by total losses. Above 1.0 is "
                      "profitable", "0.85 (best), 1.0 is the target"],
    ["Win rate", "Percentage of trades that made money", "about 45 to 48 "
                                                         "percent"],
    ["Sharpe ratio", "Return per unit of risk, annualised. Negative means "
                     "losing", "-1.82 (best)"],
    ["Max drawdown", "Worst peak-to-trough fall - the pain threshold",
     "Rs. 11,245 (best)"],
], widths=[32 * mm, 78 * mm, 55 * mm]))
A(PageBreak())

# ---- 10 findings and limits
A(H1("10. The findings, including the one we are most proud of"))
A(H2("A. The noise floor"))
A(P("After the ablation, the remaining configurations differ by about "
    "Rs. 5,000 a year, and which one wins flips between 2020 and 2021. That "
    "means we can no longer tell them apart from luck. We call this the "
    "<b>trade-management noise floor</b>: about -Rs. 10,000 to -Rs. 16,000 a "
    "year. More tuning of stops and thresholds would just be fitting our "
    "settings to two particular years."))
A(H2("B. The label / cost mismatch - our best idea for the next phase"))
A(P("This one emerged while writing the theory paper. Our model is trained to "
    "answer:"))
A(P("<i>'Will the price be more than 0.1 percent higher in 15 minutes?'</i>"))
A(P("But the trading system needs the answer to:"))
A(P("<i>'Will the price rise more than about 1.5 percent - the break-even "
    "move - before my stop or my time limit?'</i>"))
A(P("These are different questions, and the first one is much easier. A model "
    "can be excellent at the first and still lose money. <b>We are training "
    "on a target that is 15 times smaller than the move we need.</b>"))
A(BOX("The fix we will test, stated as a prediction",
      ["Raise the deadband towards the real cost hurdle, or better, use "
       "triple-barrier labelling: mark a sample as a win only if the price "
       "hits the profit target before hitting the stop, within the time "
       "limit. Then the label is literally the trade.",
       "<b>Prediction:</b> headline accuracy will fall, and profit per trade "
       "will rise. If that does not happen, our explanation of why we lose "
       "money is wrong and we will say so."], "ask"))
A(H2("C. What we are honest about (list these before the panel does)"))
A(TABLE([
    ["Limitation", "Why it matters", "What we do about it"],
    ["We ran 13 experiments and picked the best settings using 2020 and 2021",
     "Try enough settings and something looks good by chance",
     "2022 to 2024 have never been touched. The final model gets exactly one "
     "run on them."],
    ["We have OHLC bars, not bid/ask quotes",
     "Our 0.25 percent slippage is an assumption, not a measurement",
     "Stated openly; real spreads would likely make results worse, not better"],
    ["When a bar spans both stop and target, we assume the stop hit first",
     "Arbitrary, but it is the pessimistic choice", "Documented"],
    ["Lot sizes came from secondary sources",
     "Profit scales directly with lot size",
     "Must be verified against NSE circulars before live use"],
    ["Only BankNifty, only 2020 and 2021 so far",
     "2020 includes the COVID crash - an unusual regime",
     "NIFTY features are built next"],
    ["The skip rule judges 'edge' from only 2 days",
     "Very noisy estimate; the benefit may be partly just less exposure",
     "A random-skip control experiment is planned"],
], widths=[47 * mm, 55 * mm, 63 * mm]))
A(PageBreak())

# ---- 11 Q&A
A(H1("11. Question bank for the presentation"))
A(P("Answers are written the way we should say them out loud - short first, "
    "detail only if they push. The five marked HIGH RISK are the ones most "
    "likely to be asked."))

A(QA("Q1. HIGH RISK - So your system loses money. Why is this a project?",
     "Because the goal of this phase was measurement, not profit. We found "
     "and removed a labelling bug, added the real cost structure and tested "
     "over full years. That cut the yearly loss by 35 times and told us "
     "exactly where the remaining gap is: Rs. 57 of cost per trade against "
     "Rs. 21 of gross edge. We now have a system whose numbers we can trust, "
     "and a specific, testable hypothesis for closing that gap."))
A(QA("Q2. HIGH RISK - Phase 1 reported 74 percent accuracy. What happened "
     "to it?",
     "That accuracy was measured on a single day and, as we discovered, "
     "against a label that could compare one contract with another. Once the "
     "label was corrected and tested across a year, the honest picture is a "
     "win rate near 45 to 48 percent with a small positive gross edge. High "
     "accuracy on the wrong question is worse than modest accuracy on the "
     "right one."))
A(QA("Q3. HIGH RISK - Why not just use a deep learning model / LSTM?",
     "Because our bottleneck is not model capacity, it is the economics of "
     "each trade and the definition of the label. A bigger model trained on "
     "a target that is 15 times smaller than the break-even move will not "
     "help. That said, an LSTM is in our planned benchmark, tested under "
     "exactly the same costs and windows as everything else."))
A(QA("Q4. HIGH RISK - How do you know you have not overfitted?",
     "Three ways. First, every trade we report comes from a day the model "
     "never saw - we retrain daily and test on the next day only. Second, we "
     "validated on 2021, a completely different year, and the conclusions "
     "held. Third, and most importantly, 2022 to 2024 have never been "
     "touched; that is our final exam and we get one attempt."))
A(QA("Q5. HIGH RISK - What is the single most important thing you learned?",
     "That in trading, the cost structure is part of the model. A 0.1 percent "
     "prediction is worthless when the toll is 1.5 percent. Every good "
     "decision we made in this phase came from taking that seriously."))
A(QA("Q6. Why 15 minutes and not 5 or 30?",
     "We tested all three on the full year. At 5 minutes the move is too "
     "small to clear the toll. At 30 minutes the position is held so long "
     "that losers get big - the average loss grew to Rs. 805 against an "
     "average win of Rs. 532. Fifteen minutes was the balance point."))
A(QA("Q7. Why do you skip 71 percent of the trading days?",
     "Because on those days the recent data shows no edge after costs, and "
     "trading without an edge has a guaranteed cost and an uncertain benefit. "
     "Not trading is a position."))
A(QA("Q8. Why did you widen the stop-loss? Is that not more risky?",
     "Counter-intuitively, no. Our data shows the 12 percent stop lost about "
     "Rs. 1,000 every time it fired, 115 times across two years, while every "
     "other exit made money. An ATM option moves 12 percent on a 0.15 percent "
     "index move, so the stop was firing on normal noise. The 30 percent stop "
     "is disaster insurance; normal exits are handled by the signal and the "
     "time limit."))
A(QA("Q9. What is calibration and why did you need it?",
     "It makes the model's confidence honest, so 0.70 really means 70 "
     "percent. We need it because every decision - whether to enter, how many "
     "lots - is a threshold on that number. We use isotonic regression fitted "
     "on two recent days the model was not trained on."))
A(QA("Q10. Why LightGBM over XGBoost or a Random Forest?",
     "Speed and missing-value handling, because we retrain more than a "
     "thousand times per experiment and our rolling features are undefined "
     "at the start of each session. Comparing it fairly against XGBoost, "
     "CatBoost, Random Forest and a logistic-regression baseline is the first "
     "task of the next phase."))
A(QA("Q11. How do you prevent look-ahead bias?",
     "Everything used to decide on day N - the model, the calibration map, "
     "the threshold, even the decision to trade at all - comes only from days "
     "before N. All rolling features look backwards. Labels look forward, so "
     "the last few minutes of each day are dropped from training."))
A(QA("Q12. What would make this profitable?",
     "In order of our own confidence: align the label with the break-even "
     "move; trade only more expensive options where the percentage cost is "
     "lower; hold slightly longer; and structurally, move from buying naked "
     "options to spreads, which cap both cost and risk per unit of exposure."))
A(QA("Q13. Is the data reliable? Where is it from?",
     "It is a public Kaggle dataset of 1-minute NSE data, 2020 to 2024, "
     "covering the option chain, index spot and futures. We treat it as "
     "research-grade: good enough for relative comparisons, not a "
     "substitute for exchange-grade tick data before going live."))
A(QA("Q14. What happens when you go live?",
     "The architecture already separates the data feed and the broker behind "
     "interfaces, so the strategy code does not change. The rollout is "
     "staged: replay, then paper trading on live data for at least two weeks, "
     "then one lot of real money only if expectancy is positive."))
A(QA("Q15. What is the war factor / event layer we keep mentioning?",
     "A single risk number from 0 to 1 built from news headlines and a manual "
     "override, which cuts position size or halts trading during wars, policy "
     "shocks, budgets and elections. It will be backtested against known "
     "events like the COVID crash and the Ukraine invasion, and judged on "
     "drawdown reduction rather than profit."))
A(PageBreak())

# ---- 12 numbers
A(H1("12. The one-page number sheet"))
A(P("If you remember nothing else, remember these. Every number is after all "
    "costs, from data the model had never seen."))
A(TABLE([
    ["Number", "What it is"],
    ["<b>-Rs. 349,791</b>", "Phase 2 baseline, full-year 2020, 4,706 trades"],
    ["<b>-Rs. 9,983</b>", "Best configuration, same year, 276 trades "
                          "(35 times better)"],
    ["<b>-Rs. 12,311 / -Rs. 16,456</b>", "Final configuration, 2020 and 2021"],
    ["<b>+Rs. 5,710</b>", "Gross profit at 15 minutes - the model does have a "
                          "small real edge"],
    ["<b>Rs. 57</b>", "Average cost per completed trade"],
    ["<b>Rs. 40 of that Rs. 57</b>", "Flat brokerage - 70 percent of our cost"],
    ["<b>1.5 percent</b>", "Break-even move on a Rs. 300 option at lot 20"],
    ["<b>0.1 percent</b>", "The move our label currently calls a win - the "
                           "mismatch"],
    ["<b>Rs. 1.16 lakh</b>", "Lost to 12 percent stop-losses across 2020 "
                             "and 2021"],
    ["<b>115</b>", "Number of times that stop fired, at about Rs. 1,000 each"],
    ["<b>71 percent</b>", "Share of days the final system refuses to trade"],
    ["<b>about 1,200</b>", "Trading days in the feature store, 2020 to 2024"],
    ["<b>2022 to 2024</b>", "The untouched holdout. Never tested. One attempt "
                            "only."],
    ["<b>93 percent</b>", "Share of individual F&O traders who lose money, "
                          "per SEBI's 2024 study"],
], widths=[45 * mm, 120 * mm]))
A(H2("The three-sentence pitch"))
A(BOX("Say this in the first minute of the presentation",
      ["We built a machine learning system that trades BankNifty options "
       "minute by minute. In this phase we found a labelling bug, added the "
       "full Indian cost structure, and tested over complete years instead of "
       "a single day - which cut our annual loss by 35 times and showed that "
       "the real obstacle is a Rs. 57 toll on every trade against a Rs. 21 "
       "edge. We now know exactly which experiment to run next: align what "
       "the model is trained to predict with the move that actually pays for "
       "the trade."]))
A(PageBreak())

# ---- 13 references
A(H1("13. Where our ideas came from"))
A(P("Useful both for the report and for answering 'is this your own idea or "
    "standard practice?' - the honest answer is that the techniques are "
    "standard and the application is ours."))
A(TABLE([
    ["Idea we used", "Source"],
    ["Option pricing, IV and the Greeks",
     "Black and Scholes (1973); Merton (1973). Implemented via "
     "py_vollib_vectorized, which uses Peter Jaeckel's 'Let's Be Rational' "
     "solver."],
    ["LightGBM and why it is fast",
     "Ke et al., 'LightGBM: A Highly Efficient Gradient Boosting Decision "
     "Tree', NeurIPS 2017."],
    ["Isotonic calibration",
     "Zadrozny and Elkan (2002); scikit-learn's Probability Calibration user "
     "guide."],
    ["Walk-forward testing",
     "Robert Pardo, 'The Evaluation and Optimization of Trading Strategies', "
     "chapter on Walk-Forward Analysis."],
    ["Triple-barrier labelling, purged cross-validation, meta-labelling",
     "Marcos Lopez de Prado, 'Advances in Financial Machine Learning' "
     "(Wiley, 2018)."],
    ["Why tight stops get hit by noise",
     "Richard Roll (1984), 'A Simple Implicit Measure of the Effective "
     "Bid-Ask Spread in an Efficient Market', Journal of Finance."],
    ["Realised volatility from intraday returns",
     "Andersen and Bollerslev (1998), 'Answering the Skeptics'."],
    ["Guarding against picking the best of many backtests",
     "Bailey and Lopez de Prado, 'The Deflated Sharpe Ratio' (2014)."],
    ["Cost rates (brokerage, STT, GST, stamp duty)",
     "Zerodha's published charges page and STT explainer."],
    ["Lot size changes",
     "NSE circular NSE/FAOP/56233, 31 March 2023 (BankNifty lot 25 to 15)."],
    ["Put-call ratio as sentiment - and its limits",
     "IIFL and Groww option-chain explainers; Harbourfront Quantitative "
     "Research on PCR reliability."],
    ["Market reality check",
     "SEBI press release, September 2024: 93 percent of individual F&O "
     "traders lost money between FY22 and FY24."],
    ["Live trading interface",
     "Fyers API v3 documentation and the fyers-apiv3 Python client."],
], widths=[55 * mm, 110 * mm]))
A(Spacer(1, 6))
A(P("Full citations with links are in the references section of the Phase 2 "
    "theory paper (docs/phase2_report.tex).", "small"))


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=24 * mm, bottomMargin=22 * mm,
                          title="Phase 2 Study Guide - NSE AI Options Bot",
                          author="Anubhaw Raj, Subham Singh, "
                                 "Harsh Raj Sharma, Nirban Das")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="body")
    doc.addPageTemplates([PageTemplate(id="std", frames=[frame],
                                       onPage=decorate)])
    doc.build(story)
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    build()
