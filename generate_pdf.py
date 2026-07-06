"""
generate_pdf.py
Generates a styled PDF of the Phase 1 Onboarding Guide using reportlab.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import re

INPUT_TXT  = r"C:\Users\anubh\.gemini\antigravity\brain\664f592f-d891-4735-ad14-82d1b1e8f5b2\phase1_onboarding_guide.txt"
OUTPUT_PDF = r"C:\Users\anubh\.gemini\antigravity\brain\664f592f-d891-4735-ad14-82d1b1e8f5b2\Phase1_Onboarding_Guide.pdf"

# ── Colour palette ──────────────────────────────────────────────────────────
DARK_BG    = colors.HexColor("#1a1a2e")
ACCENT     = colors.HexColor("#e94560")
LIGHT_BLUE = colors.HexColor("#0f3460")
GOLD       = colors.HexColor("#f5a623")
WHITE      = colors.white
LIGHT_GRAY = colors.HexColor("#f0f0f0")
MID_GRAY   = colors.HexColor("#cccccc")
TEXT_DARK  = colors.HexColor("#1a1a1a")

doc = SimpleDocTemplate(
    OUTPUT_PDF,
    pagesize=A4,
    rightMargin=2*cm, leftMargin=2*cm,
    topMargin=2.5*cm, bottomMargin=2.5*cm,
)

styles = getSampleStyleSheet()

# ── Custom styles ────────────────────────────────────────────────────────────
title_style = ParagraphStyle(
    "DocTitle",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=20,
    textColor=WHITE,
    alignment=TA_CENTER,
    spaceAfter=6,
    leading=26,
)
subtitle_style = ParagraphStyle(
    "DocSubtitle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=11,
    textColor=GOLD,
    alignment=TA_CENTER,
    spaceAfter=4,
)
section_style = ParagraphStyle(
    "SectionHead",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=13,
    textColor=WHITE,
    spaceAfter=6,
    spaceBefore=14,
    leftIndent=0,
)
subsection_style = ParagraphStyle(
    "SubHead",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=11,
    textColor=ACCENT,
    spaceAfter=4,
    spaceBefore=10,
)
body_style = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=10,
    textColor=TEXT_DARK,
    leading=15,
    spaceAfter=5,
)
bullet_style = ParagraphStyle(
    "Bullet",
    parent=body_style,
    leftIndent=18,
    bulletIndent=6,
    spaceBefore=2,
    spaceAfter=2,
)
code_style = ParagraphStyle(
    "Code",
    parent=styles["Normal"],
    fontName="Courier",
    fontSize=9,
    textColor=colors.HexColor("#2d2d2d"),
    backColor=colors.HexColor("#f5f5f5"),
    leading=13,
    leftIndent=12,
    rightIndent=12,
    spaceAfter=4,
    spaceBefore=4,
    borderPad=4,
)
table_key_style = ParagraphStyle(
    "TableKey",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=WHITE,
)
table_val_style = ParagraphStyle(
    "TableVal",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    textColor=TEXT_DARK,
    leading=13,
)

def make_title_block():
    """Returns a styled title table with dark background."""
    title_data = [[
        Paragraph("PHASE 1 ONBOARDING GUIDE", title_style),
    ], [
        Paragraph("NSE AI Options Bot — A Plain English Explanation for New Team Members", subtitle_style),
    ]]
    t = Table(title_data, colWidths=[17*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BG),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [DARK_BG]),
    ]))
    return t

def make_section_header(text):
    """Dark-background section banner."""
    p = Paragraph(text, section_style)
    t = Table([[p]], colWidths=[17*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("LINEBELOW", (0,0), (-1,-1), 2, ACCENT),
    ]))
    return t

def make_greeks_table():
    headers = ["Greek", "What It Means (Simple English)"]
    rows = [
        ["DELTA",  "If BankNifty moves ₹1, my option moves ₹X. Tells us directional exposure. The #1 most important feature in our model (56.9% importance)."],
        ["GAMMA",  "How fast is Delta itself changing? High Gamma = option is very sensitive near expiry. Think of it as the acceleration of the option."],
        ["THETA",  "How much value does my option LOSE per day just by waiting? Always negative. This caused our first major problem (Theta Decay Bias)."],
        ["VEGA",   "If market volatility rises 1%, how does my option price change? High Vega = sensitive to volatility spikes from news or policy events."],
        ["RHO",    "Sensitivity to interest rate changes. Least important Greek in short-term intraday trading."],
    ]
    data = [[Paragraph(h, ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE))
             for h in headers]]
    for greek, desc in rows:
        data.append([
            Paragraph(greek, ParagraphStyle("TK", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
            Paragraph(desc,  table_val_style),
        ])
    t = Table(data, colWidths=[3*cm, 14*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
        ("BACKGROUND",    (0,1), (-1,-1), LIGHT_GRAY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [LIGHT_GRAY, WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.4, MID_GRAY),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return t

def make_problems_table():
    data = [
        [Paragraph("PROBLEM", ParagraphStyle("PH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
         Paragraph("WHAT HAPPENED", ParagraphStyle("PH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
         Paragraph("THE FIX", ParagraphStyle("PH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE))],
        [Paragraph("1. Theta Decay Bias", ParagraphStyle("PK", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
         Paragraph("Regression model always predicted negative returns because options naturally decay every minute. Zero BUY signals generated.", table_val_style),
         Paragraph("Switched from Regression to Binary Classification. Now the model predicts UP/DOWN direction only, bypassing the decay bias entirely.", table_val_style)],
        [Paragraph("2. Absolute Price Overfitting", ParagraphStyle("PK", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
         Paragraph("Model used raw option price (close_opt) for 84.8% of its decisions — memorizing price levels instead of learning real market dynamics.", table_val_style),
         Paragraph("Removed all absolute prices. Replaced with 1-minute and 5-minute momentum returns. Feature importance shifted to Delta (56.9%) — correct!", table_val_style)],
    ]
    t = Table(data, colWidths=[3.8*cm, 6.6*cm, 6.6*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
        ("BACKGROUND",    (0,1), (0,-1),  colors.HexColor("#fff0f0")),
        ("BACKGROUND",    (1,1), (-1,-1), LIGHT_GRAY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#fff8f8"), WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.4, MID_GRAY),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return t

def make_metrics_table():
    data = [
        [Paragraph("Metric", ParagraphStyle("MH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
         Paragraph("Value", ParagraphStyle("MH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
         Paragraph("What It Tells Us", ParagraphStyle("MH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE))],
        ["Model Accuracy", "74.6%",  "Out of all UP/DOWN predictions, 74.6% were correct."],
        ["Total Trades",   "10",     "The state machine executed 10 trades in the single test day."],
        ["Win Rate",       "40%",    "4 out of 10 trades were profitable."],
        ["Avg Win",        "₹188",   "Average rupee profit on a winning trade (× lot size of 25)."],
        ["Avg Loss",       "₹212",   "Average rupee loss on a losing trade."],
        ["Net PnL",        "−₹516",  "Total day PnL. Negative because avg loss > avg win. Fixed in Phase 2."],
    ]
    col_data = []
    for i, row in enumerate(data):
        if i == 0:
            col_data.append(row)
        else:
            col_data.append([
                Paragraph(row[0], ParagraphStyle("MK", fontName="Helvetica-Bold", fontSize=9, textColor=LIGHT_BLUE)),
                Paragraph(row[1], ParagraphStyle("MV", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
                Paragraph(row[2], table_val_style),
            ])
    t = Table(col_data, colWidths=[4*cm, 2.5*cm, 10.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [LIGHT_GRAY, WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.4, MID_GRAY),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t

# ── Build story ──────────────────────────────────────────────────────────────
story = []

story.append(make_title_block())
story.append(Spacer(1, 0.5*cm))

# ── Sec 0: Big Picture ───────────────────────────────────────────────────────
story.append(make_section_header("SECTION 0 — WHAT IS THE BIG PICTURE GOAL?"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "Imagine you are a trader at 9:15 AM every morning watching BankNifty — an index "
    "tracking India's top 12 banking stocks (HDFC, ICICI, SBI, etc.). This index moves "
    "wildly, sometimes 500–1000 points in a single session. You want to make money by "
    "trading <b>OPTIONS</b> on this index.", body_style))
story.append(Paragraph(
    "An option is a contract giving you the right (but not the obligation) to buy or sell "
    "an asset at a fixed price on a specific date. Think of it like insurance — you pay a "
    "small premium, and if the market moves your way, you profit enormously.", body_style))
story.append(Paragraph(
    "<b>The BIG QUESTION our system answers every minute:</b>", body_style))

q_data = [[Paragraph(
    '"For the next 5 minutes, will this option\'s price go UP or DOWN?"',
    ParagraphStyle("Quote", fontName="Helvetica-BoldOblique", fontSize=12,
                   textColor=DARK_BG, alignment=TA_CENTER))]]
q_table = Table(q_data, colWidths=[17*cm])
q_table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), GOLD),
    ("TOPPADDING", (0,0), (-1,-1), 12),
    ("BOTTOMPADDING", (0,0), (-1,-1), 12),
]))
story.append(q_table)
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "If our AI correctly answers this even 55–60% of the time, we can build a profitable "
    "automated trading system around it. That is the entire goal of Phase 1.", body_style))

# ── Sec 1: Dataset ───────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 1 — THE DATASET"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "We have historical <b>1-minute tick data</b> from NSE for BankNifty starting January 2020. "
    "The data comes in <b>two separate files</b> for each trading day:", body_style))
story.append(Paragraph("• <b>Spot Data</b> — 1-minute OHLC prices of the BankNifty index itself (the true reference point).", bullet_style))
story.append(Paragraph("• <b>Options Chain Data</b> — 1-minute OHLC for thousands of individual options contracts across all strikes and expiries.", bullet_style))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "Each contract is uniquely identified by its symbol, e.g.:", body_style))
story.append(Paragraph("BANKNIFTY16JAN2032200CE", code_style))
story.append(Paragraph("This encodes: underlying (BANKNIFTY), expiry (16 Jan 2020), strike (32200), type (CE = Call).", body_style))
story.append(Paragraph(
    "Key columns and their significance:", body_style))
story.append(Paragraph("• <b>Symbol/Ticker</b> — Parsed to extract strike price and option type (CE/PE).", bullet_style))
story.append(Paragraph("• <b>Date & Time</b> — Used to calculate precise Time-to-Expiry (TTE) down to the second.", bullet_style))
story.append(Paragraph("• <b>Close Price</b> — The last traded price that minute. Later transformed into momentum returns.", bullet_style))
story.append(Paragraph("• <b>Volume</b> — Contracts traded that minute. High volume = liquid = less slippage.", bullet_style))
story.append(Paragraph("• <b>Open Interest (OI)</b> — Total unsettled contracts. Shifts in OI reveal institutional positioning.", bullet_style))

# ── Sec 2: Data Pipeline ─────────────────────────────────────────────────────
story.append(make_section_header("SECTION 2 — THE DATA PIPELINE & LOOK-AHEAD BIAS"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "<b>Look-ahead bias</b> is the #1 cardinal sin in quantitative finance. It occurs when "
    "a model accidentally accesses future data during training, making it seem accurate in "
    "testing but completely useless in live trading.", body_style))
story.append(Paragraph(
    "Our pipeline prevents this with a strict <b>Rolling Window</b> approach — data is "
    "processed strictly in chronological order. The model is NEVER allowed to see any data "
    "from its future. In Phase 1 we used:", body_style))
story.append(Paragraph("• <b>Train:</b> 7 days (Jan 1–9, 2020)", bullet_style))
story.append(Paragraph("• <b>Test:</b>  1 day  (Jan 10, 2020) — data the model has never seen", bullet_style))

# ── Sec 3: Greeks ────────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 3 — THE GREEKS (BSM Framework)"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "Raw option prices are useless for ML because they are non-stationary (₹250 on Day 1 "
    "and ₹250 on Day 50 mean completely different things). The solution is the "
    "<b>Black-Scholes-Merton (BSM) framework</b> — a Nobel Prize-winning formula that "
    "decomposes every option's price into 5 universal sensitivity measures called <b>the Greeks</b>:", body_style))
story.append(Spacer(1, 0.2*cm))
story.append(make_greeks_table())
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "We also back-calculate <b>Implied Volatility (IV)</b> — the market's real-time fear gauge. "
    "High IV means traders expect big moves (e.g., RBI policy day). Low IV means a calm market. "
    "All of these become feature columns in our training data, computed via <i>py_vollib_vectorized</i>.", body_style))

# ── Sec 4: Model ─────────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 4 — THE MACHINE LEARNING MODEL (GBM Classifier)"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "We use a <b>Gradient Boosting Machine (GBM) Classifier</b>. Here is how it works in plain English:", body_style))
story.append(Paragraph("1. Build a tiny, simple decision tree. It predicts UP/DOWN but badly. Record all mistakes.", bullet_style))
story.append(Paragraph("2. Build a SECOND tree that specifically corrects the mistakes of the first one.", bullet_style))
story.append(Paragraph("3. Build a THIRD tree that fixes the errors of the first two.", bullet_style))
story.append(Paragraph("4. Repeat 300 times. The final model is a committee of 300 small trees, each specializing in fixing the previous ones' errors.", bullet_style))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "The model output is a <b>probability score P(UP)</b> for every single minute:", body_style))
story.append(Paragraph("• P(UP) = 0.67 → Model is 67% confident price will rise in 5 minutes → likely BUY signal", bullet_style))
story.append(Paragraph("• P(UP) = 0.31 → Only 31% confident → price likely falling → no entry", bullet_style))
story.append(Paragraph(
    "This probability is what drives all trading decisions through the State Machine (Section 5).", body_style))

# ── Sec 5: Problems ──────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 5 — PROBLEMS DISCOVERED & HOW WE SOLVED THEM"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "We did not get a working model on the first try. Here are the two critical problems "
    "we discovered and the exact mathematical fixes applied:", body_style))
story.append(Spacer(1, 0.2*cm))
story.append(make_problems_table())

# ── Sec 6: State Machine ─────────────────────────────────────────────────────
story.append(make_section_header("SECTION 6 — THE STATE MACHINE (Trading Engine)"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "Once the model produces P(UP) probabilities for every minute, the <b>Position State Machine</b> "
    "(in <i>src/simulator.py</i>) decides exactly when to enter and exit trades:", body_style))
story.append(Paragraph("• At 9:15 AM, identify the <b>ATM (At-The-Money) contract</b> — the strike closest to the current spot price. Lock onto it for the whole day.", bullet_style))
story.append(Paragraph("• Every minute, receive the model's P(UP) probability.", bullet_style))
story.append(Spacer(1, 0.1*cm))

sm_data = [
    [Paragraph("Current State", ParagraphStyle("SMH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
     Paragraph("Condition", ParagraphStyle("SMH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
     Paragraph("Action", ParagraphStyle("SMH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE))],
    [Paragraph("OUT (no position)", table_val_style),
     Paragraph("P(UP) > 0.52", table_val_style),
     Paragraph("BUY the option → transition to IN state", table_val_style)],
    [Paragraph("OUT (no position)", table_val_style),
     Paragraph("P(UP) ≤ 0.52", table_val_style),
     Paragraph("Do nothing, stay OUT", table_val_style)],
    [Paragraph("IN (holding position)", table_val_style),
     Paragraph("P(UP) < 0.48", table_val_style),
     Paragraph("SELL → exit position, transition to OUT", table_val_style)],
    [Paragraph("IN (holding position)", table_val_style),
     Paragraph("Held > 10 minutes", table_val_style),
     Paragraph("SELL (time-stop, don't overstay)", table_val_style)],
    [Paragraph("IN (holding position)", table_val_style),
     Paragraph("Time = 3:15 PM", table_val_style),
     Paragraph("SELL (mandatory market close exit)", table_val_style)],
]
sm_table = Table(sm_data, colWidths=[4*cm, 4.5*cm, 8.5*cm])
sm_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [LIGHT_GRAY, WHITE]),
    ("GRID",          (0,0), (-1,-1), 0.4, MID_GRAY),
    ("TOPPADDING",    (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(sm_table)
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "<b>PnL per trade</b> = (Exit Price − Entry Price) × 25 (BankNifty lot size). "
    "For example: Bought at ₹290, Sold at ₹304 → PnL = ₹14 × 25 = <b>₹350 profit</b>.", body_style))

# ── Sec 7: Output ────────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 7 — THE OUTPUT & WHAT IT MEANS"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph("The pipeline generates a <b>4-panel simulation chart</b>:", body_style))
story.append(Paragraph("• <b>Panel 1 (Top Left)</b> — ATM Option Price with green ▲ entry and red ▼ exit markers, purple shaded holding periods.", bullet_style))
story.append(Paragraph("• <b>Panel 2 (Top Right)</b> — Raw P(UP) probability line (amber). Green zone = BUY zone (>0.52). Red zone = EXIT zone (<0.48).", bullet_style))
story.append(Paragraph("• <b>Panel 3 (Bottom Left)</b> — Cumulative running PnL across all trades for the day.", bullet_style))
story.append(Paragraph("• <b>Panel 4 (Bottom Right)</b> — Per-trade PnL distribution histogram showing size of each win and loss.", bullet_style))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph("<b>Phase 1 Final Results (Jan 10, 2020 test day):</b>", body_style))
story.append(make_metrics_table())

# ── Sec 8: Files ─────────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 8 — CODE FILE MAP"))
story.append(Spacer(1, 0.2*cm))

files = [
    ("main.py", "Master runner. Execute this to kick off the full pipeline end-to-end."),
    ("src/feature_engineering.py", "Reads raw CSVs, merges Spot + Options, calculates all Greeks and momentum returns."),
    ("src/model.py", "Defines the GBM Classifier, trains it, evaluates on test day, returns P(UP) probabilities."),
    ("src/simulator.py", "The Position State Machine. Executes trades based on probabilities. Generates the 4-panel chart."),
    ("data/raw_option_chain/", "Raw CSV files organized by year and month."),
    ("data/processed_features/", "Generated simulation charts and processed feature files."),
]
file_data = [[
    Paragraph("File / Folder", ParagraphStyle("FH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
    Paragraph("Purpose", ParagraphStyle("FH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
]]
for fname, purpose in files:
    file_data.append([
        Paragraph(fname, ParagraphStyle("FC", fontName="Courier", fontSize=8, textColor=ACCENT)),
        Paragraph(purpose, table_val_style),
    ])
file_table = Table(file_data, colWidths=[6*cm, 11*cm])
file_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [LIGHT_GRAY, WHITE]),
    ("GRID",          (0,0), (-1,-1), 0.4, MID_GRAY),
    ("TOPPADDING",    (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(file_table)

# ── Sec 9: Roadmap ───────────────────────────────────────────────────────────
story.append(make_section_header("SECTION 9 — PHASE 2 ROADMAP"))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph("Phase 1 is complete. Here is what comes next:", body_style))
story.append(Paragraph("1. <b>Phase 2 — Real Trading Costs:</b> Add STT, exchange fees, and bid-ask slippage to every trade to calculate real net PnL.", bullet_style))
story.append(Paragraph("2. <b>Phase 3 — Big Data Run:</b> Expand the rolling window across 3–6 months of data to prove statistical significance.", bullet_style))
story.append(Paragraph("3. <b>Phase 4 — Hyperparameter Optimization:</b> Grid Search to find the mathematically optimal entry/exit thresholds.", bullet_style))
story.append(Paragraph("4. <b>Phase 5 — Multi-Directional Execution:</b> Trade both ATM CE (calls) and ATM PE (puts) to profit in both rising and falling markets.", bullet_style))

# ── Footer divider ───────────────────────────────────────────────────────────
story.append(Spacer(1, 0.5*cm))
story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT))
footer_data = [[Paragraph(
    "Phase 1 Onboarding Guide  |  NSE AI Options Bot  |  Questions? Ask the team lead.",
    ParagraphStyle("Footer", fontName="Helvetica", fontSize=8, textColor=colors.gray, alignment=TA_CENTER)
)]]
footer_t = Table(footer_data, colWidths=[17*cm])
footer_t.setStyle(TableStyle([("TOPPADDING",(0,0),(-1,-1),6)]))
story.append(footer_t)

# ── Build PDF ────────────────────────────────────────────────────────────────
doc.build(story)
print("PDF saved -> " + OUTPUT_PDF)
