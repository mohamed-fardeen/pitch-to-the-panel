import io

import matplotlib
from reportlab.lib.colors import HexColor, lightgrey
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Use non-GUI backend
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from orchestrator import AGENTS_CONFIG


def create_score_chart(memory: dict) -> io.BytesIO:
    """Generate a performance score bar chart based on memory extraction."""
    # Logic: 1 strength = 2 pts, 1 risk = -2 pts (base 5), capped 1-10
    s_count = len(memory.get("strengths", []))
    r_count = len(memory.get("risks", []))
    c_count = len(memory.get("claims", []))
    o_count = len(memory.get("opinions", []))

    # Simple normalization math (1-10 scale)
    def normalize(val, factor=2): return min(10, max(1, 4 + (val * factor)))

    scores = {
        "Strength": normalize(s_count, 1.5),
        "Risk Mitigation": min(10, max(1, 10 - (r_count * 1.5))),
        "Clarity": normalize(c_count, 1.2),
        "Panel Interest": normalize(o_count, 0.8)
    }

    fig, ax = plt.subplots(figsize=(6, 3))
    colors = ['#047857', '#B91C1C', '#1E40AF', '#B45309']

    bars = ax.bar(scores.keys(), scores.values(), color=colors, alpha=0.85)
    ax.set_ylim(0, 10)
    ax.set_yticks(range(0, 11, 2))
    ax.set_title('AI Strategic Evaluation Score', fontsize=12, fontweight='bold', pad=15)
    ax.grid(axis='y', linestyle='--', alpha=0.3)

    # Add values on top
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f'{int(bar.get_height())}/10', ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf

def create_risk_ratio_chart(memory: dict) -> io.BytesIO:
    """Generate a Risk vs Strength donut chart."""
    s_count = len(memory.get("strengths", []))
    r_count = len(memory.get("risks", []))

    if s_count == 0 and r_count == 0:
        s_count, r_count = 1, 1 # Dummy for visual

    labels = ['Strengths', 'Risks']
    sizes = [s_count, r_count]
    colors = ['#10B981', '#EF4444']

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140,
           colors=colors, wedgeprops={'width': 0.4, 'edgecolor': 'w'})

    ax.set_title('Strategic Balance Overview', fontsize=10, fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf

def create_participation_chart(conversation: list) -> io.BytesIO:
    """Generate a panel participation bar chart."""
    counts = {}
    for turn in conversation:
        name = turn.get("agent_name", "Unknown")
        if "pitcher" in turn.get("type", "").lower() or name.lower() == "pitcher":
            name = "Founder"
        counts[name] = counts.get(name, 0) + 1

    names = list(counts.keys())
    values = list(counts.values())

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(names, values, color='#6366F1', alpha=0.7)
    ax.set_xlabel('Message Frequency', fontsize=9)
    ax.set_title('Panel Participation Analysis', fontsize=11, fontweight='bold')
    ax.grid(axis='x', linestyle=':', alpha=0.5)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf

async def generate_pdf_report(session: dict) -> bytes:
    """Generate professional professional, demo-ready pitch evaluation report as PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=20*mm, bottomMargin=20*mm,
                             leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()

    # Custom Brand Colors
    brand_blue = HexColor('#1E40AF') # Bold Blue
    danger_red = HexColor('#B91C1C') # Dark Red
    success_green = HexColor('#047857') # Dark Green
    warning_gold = HexColor('#B45309') # Dark Gold
    slate_900 = HexColor('#0F172A')
    slate_600 = HexColor('#475569')
    slate_50 = HexColor('#F8FAFC')

    # Styles
    title_style = ParagraphStyle('title', fontSize=26, textColor=slate_900,
                                parent=styles['Heading1'], alignment=TA_CENTER,
                                spaceAfter=15, fontName='Helvetica-Bold')

    h1_style = ParagraphStyle('h1', fontSize=16, textColor=brand_blue,
                             parent=styles['Heading2'], spaceBefore=15, spaceAfter=8,
                             fontName='Helvetica-Bold')

    h2_style = ParagraphStyle('h2', fontSize=13, textColor=slate_900,
                             parent=styles['Heading3'], spaceBefore=10, spaceAfter=5,
                             fontName='Helvetica-Bold')

    body_style = ParagraphStyle('body', fontSize=11, textColor=slate_900,
                               lineSpacing=1.2, spaceAfter=10)

    bullet_style = ParagraphStyle('bullet', parent=body_style, leftIndent=15, bulletIndent=5,
                                 bulletText='•', spaceAfter=6)

    content = []

    # --- PAGE 1: EXECUTIVE SUMMARY ---
    # 1. TITLE
    content.append(Paragraph("Pitch Evaluation Report", title_style))
    content.append(HRFlowable(width="100%", thickness=2, color=brand_blue, spaceAfter=10))

    # 2. PITCH SUMMARY
    content.append(Paragraph("Executive Summary", h1_style))
    refined_pitch = session.get("refined_pitch") or session.get("pitch_summary", "No pitch data available.")
    content.append(Paragraph(refined_pitch, body_style))
    content.append(Spacer(1, 10))

    # 3. PANEL OVERVIEW
    content.append(Paragraph("Panel Composition", h2_style))
    active_panel = session.get("domain", {}).get("active_panel", session.get("active_panel", []))
    if active_panel:
        panel_data = []
        for agent_id in active_panel:
            if agent_id in AGENTS_CONFIG:
                cfg = AGENTS_CONFIG[agent_id]
                panel_data.append([
                    Paragraph(f"<b>{cfg['name']}</b>", body_style),
                    Paragraph(cfg['role'], body_style)
                ])

        pt = Table(panel_data, colWidths=[50*mm, 120*mm])
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), slate_50),
            ('GRID', (0, 0), (-1, -1), 0.5, lightgrey),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(pt)
    content.append(Spacer(1, 10))

    # --- PERFORMANCE OVERVIEW (CHARTS) ---
    content.append(Paragraph("AI Evaluation Analytics", h1_style))
    memory = session.get("memory", {})
    conversation = session.get("conversation", [])

    # Score Chart (Bar)
    score_buf = create_score_chart(memory)
    content.append(Image(score_buf, width=160*mm, height=80*mm))
    content.append(Spacer(1, 10))

    # Donut + Participation in a table for side-by-side feel if possible, but Simple Table is easier
    chart_table_data = [
        [
            Image(create_risk_ratio_chart(memory), width=80*mm, height=80*mm),
            Image(create_participation_chart(conversation), width=90*mm, height=50*mm)
        ]
    ]
    ct = Table(chart_table_data, colWidths=[85*mm, 85*mm])
    ct.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    content.append(ct)
    content.append(Spacer(1, 10))

    content.append(PageBreak())

    # --- PAGE 2: STRATEGIC INSIGHTS ---
    # 4. KEY INSIGHTS
    if any(memory.get(k) for k in memory):
        content.append(Paragraph("Phase 1: Strategic Insights", h1_style))

        insight_sections = [
            ("Strengths", "strengths", success_green, "✓"),
            ("Risks & Hazards", "risks", danger_red, "⚠"),
            ("Core Claims", "claims", brand_blue, "→"),
            ("Contradictions", "contradictions", warning_gold, "⁈"),
            ("Topic Opinions", "opinions", slate_900, "•")
        ]

        for title, key, color, icon in insight_sections:
            items = memory.get(key, [])
            if items:
                content.append(Paragraph(title, ParagraphStyle('h_sub', fontSize=12, textColor=color, fontName='Helvetica-Bold', spaceBefore=5)))
                for item in items:
                    content.append(Paragraph(f"{icon} {item}", ParagraphStyle('insight_bullet', fontSize=10.5, textColor=slate_900, leftIndent=12, spaceAfter=4)))
                content.append(Spacer(1, 5))

    # 5. PANEL DISCUSSION
    content.append(Paragraph("Phase 2: Transcript Analysis", h1_style))
    if conversation:
        conv_data = []
        for turn in conversation:
            agent_name = turn.get("agent_name", "Unknown")
            agent_id = turn.get("agent_id")
            role_text = ""
            if agent_id and agent_id in AGENTS_CONFIG:
                role_text = f" ({AGENTS_CONFIG[agent_id]['role']})"

            speaker_style = ParagraphStyle('speaker', fontSize=10, textColor=brand_blue, fontName='Helvetica-Bold')
            if "pitcher" in turn.get("type", "").lower() or "pitcher" in agent_name.lower():
                speaker_style = ParagraphStyle('speaker_pitcher', fontSize=10, textColor=slate_600, fontName='Helvetica-Bold')

            content_style = ParagraphStyle('c_body', fontSize=10, textColor=slate_900, leftIndent=5)
            conv_data.append([
                Paragraph(f"{agent_name}{role_text}", speaker_style),
                Paragraph(turn.get("content", ""), content_style)
            ])

        t_conv = Table(conv_data, colWidths=[40*mm, 130*mm])
        t_conv.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 0.2, lightgrey),
        ]))
        content.append(t_conv)

    # 6. GAPS, VERDICT, BLACK SWAN - Continue...
    content.append(PageBreak())

    # 6. CRITICAL GAPS
    reflection = session.get("reflection", {})
    missing = reflection.get("missing", [])
    if missing:
        content.append(Paragraph("Strategic Knowledge Gaps", h1_style))
        for gap in missing:
            content.append(Paragraph(gap, bullet_style))
        content.append(Spacer(1, 10))

    # 7. FINAL VERDICT
    verdict = session.get("verdict")
    verdict_parts = session.get("verdict_parts", {})
    if verdict_parts or verdict:
        content.append(HRFlowable(width="100%", thickness=1, color=brand_blue, spaceBefore=20))
        content.append(Paragraph("Investment Verdict", h1_style))

        if verdict_parts:
            v_items = [
                ("Strongest Strategic Advantage", verdict_parts.get("strongest", ""), success_green),
                ("Primary Risk Factor", verdict_parts.get("weakness", ""), danger_red),
                ("Immediate Recommendation", verdict_parts.get("fix", ""), brand_blue),
            ]
            for label, val, color in v_items:
                if val:
                    content.append(Paragraph(label, ParagraphStyle('v_l', fontSize=9, textColor=color, fontName='Helvetica-Bold')))
                    content.append(Paragraph(val, body_style))
        elif verdict:
            content.append(Paragraph(verdict, body_style))

    # 8. BLACK SWAN
    black_swan = session.get("black_swan_insight") or session.get("black_swan")
    if black_swan:
        content.append(Spacer(1, 10))
        content.append(Paragraph("Black Swan Signal Table", h1_style))
        if isinstance(black_swan, dict):
            finding = black_swan.get("black_swan_finding", "")
            content.append(Paragraph(f"<b>Hypothesis:</b> {finding}", body_style))
            content.append(Paragraph(f"<b>Evidence:</b> {black_swan.get('evidence', '')}", body_style))
        else:
            content.append(Paragraph(str(black_swan), body_style))

    # 9. AI PITCH REVISION (Phase 4)
    revised_pitch = session.get("revised_pitch")
    if revised_pitch:
        content.append(PageBreak())
        content.append(HRFlowable(width="100%", thickness=2, color=brand_blue, spaceBefore=0))
        content.append(Spacer(1, 12))
        content.append(Paragraph("AI-Powered Pitch Revision", h1_style))
        content.append(Paragraph(
            "The following is a revised version of the original pitch, rewritten by the AI coach "
            "to directly address the panel's criticisms and close identified gaps.",
            body_style
        ))
        content.append(Spacer(1, 10))

        # Original pitch box
        content.append(Paragraph("Original Pitch", ParagraphStyle(
            'orig_label', fontSize=9, textColor=danger_red, fontName='Helvetica-Bold', spaceAfter=4
        )))
        original = session.get("pitch_summary", "")
        orig_style = ParagraphStyle('orig_box', fontSize=10, leading=15,
                                    textColor=HexColor('#374151'),
                                    backColor=HexColor('#FEF2F2'),
                                    borderPad=10, leftIndent=10, rightIndent=10,
                                    spaceAfter=12)
        content.append(Paragraph(original, orig_style))

        # Revised pitch box
        content.append(Paragraph("Revised Pitch", ParagraphStyle(
            'rev_label', fontSize=9, textColor=success_green, fontName='Helvetica-Bold', spaceAfter=4
        )))
        rev_style = ParagraphStyle('rev_box', fontSize=10, leading=15,
                                   textColor=HexColor('#374151'),
                                   backColor=HexColor('#ECFDF5'),
                                   borderPad=10, leftIndent=10, rightIndent=10,
                                   spaceAfter=12)
        content.append(Paragraph(revised_pitch, rev_style))

        # Improvements addressed
        verdict_parts = session.get("verdict_parts", {})
        improvements = [
            verdict_parts.get("weakness", ""),
            verdict_parts.get("fix", ""),
        ]
        improvements = [i for i in improvements if i]
        if improvements:
            content.append(Paragraph("Issues Addressed in Revision", ParagraphStyle(
                'imp_label', fontSize=9, textColor=brand_blue, fontName='Helvetica-Bold', spaceAfter=6
            )))
            for imp in improvements:
                content.append(Paragraph(f"✓  {imp}", bullet_style))

    doc.build(content)
    buffer.seek(0)
    return buffer.read()

