from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import mm
import io, base64
from orchestrator import AGENTS_CONFIG, generate_radar_chart_image

async def generate_pdf_report(session: dict) -> bytes:
    """Generate complete pitch report as PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=15*mm, bottomMargin=15*mm,
                             leftMargin=15*mm, rightMargin=15*mm)
    
    styles = getSampleStyleSheet()
    brand = HexColor('#1A56DB')
    dark = HexColor('#111827')
    gray = HexColor('#6B7280')
    light = HexColor('#F3F4F6')
    
    content = []
    
    # Header
    header_style = ParagraphStyle('header', fontSize=20, textColor=white,
                                   backColor=HexColor('#1E3A5F'), 
                                   spaceAfter=6, spaceBefore=0,
                                   leftIndent=10, rightIndent=10)
    content.append(Paragraph("EchoChamber AI — Focus Group Analysis Report", header_style))
    content.append(Spacer(1, 10))
    
    # Pitch summary
    content.append(Paragraph("What you pitched:", 
                              ParagraphStyle('label', fontSize=10, textColor=gray)))
    content.append(Paragraph(session.get("pitch_summary", "No summary provided."), 
                              ParagraphStyle('body', fontSize=11, textColor=dark, 
                                            spaceAfter=10)))
    content.append(Spacer(1, 6))
    
    # Radar chart if available
    if session.get("scores"):
        chart_b64 = await generate_radar_chart_image(session["scores"])
        if chart_b64:
            chart_data = base64.b64decode(chart_b64)
            chart_img = io.BytesIO(chart_data)
            content.append(Image(chart_img, width=80*mm, height=80*mm))
            content.append(Spacer(1, 6))
            content.append(Paragraph("Scores reflect panel evaluation based on responses and reasoning.", 
                                      ParagraphStyle('chart_cap', fontSize=9, textColor=gray, alignment=1)))
            content.append(Spacer(1, 10))
    
    # Agent responses summary
    content.append(Paragraph("What the panel said:", 
                              ParagraphStyle('section', fontSize=12, textColor=brand,
                                            spaceBefore=8, spaceAfter=4)))
    
    agent_data = []
    for turn in session.get("conversation", []):
         turn_type = turn.get("type", "")
         if turn_type in ["question", "reaction", "interrupt_q", "persona_response", "debate", "rebuttal", "answer"] or (turn.get("agent_name") and "system" not in turn.get("agent_name", "").lower()):
             agent_id = turn.get("agent_id")
             raw_name = turn.get("agent_name", "Panelist")
             
             role = ""
             if agent_id and agent_id in AGENTS_CONFIG:
                 base_role = AGENTS_CONFIG[agent_id].get("role", "")
                 if base_role:
                     role = f" ({base_role})"
             agent_name = f"{raw_name}{role}"
             
             response = turn.get("content", "")
             if len(response) > 500: response = response[:500] + "..."
             agent_data.append([
                 Paragraph(agent_name, ParagraphStyle('agent', fontSize=9, textColor=brand)),
                 Paragraph(response, ParagraphStyle('resp', fontSize=9, textColor=dark))
             ])
    
    if agent_data:
        t = Table(agent_data, colWidths=[35*mm, 130*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), light),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        content.append(t)
        content.append(Spacer(1, 10))
    
    # Key Insights
    content.append(Paragraph("Key Insights from Panel", 
                              ParagraphStyle('section', fontSize=12, textColor=brand, spaceBefore=8, spaceAfter=4)))
    
    key_insights = session.get("key_insights", [])
    if not key_insights:
        key_insights = ["No key insights generated."]
            
    for ins in key_insights:
        content.append(Paragraph(ins, ParagraphStyle('insight_bullet', fontSize=10, textColor=dark, leftIndent=10, spaceAfter=2)))
    content.append(Spacer(1, 10))
    
    # Verdict
    parts = session.get("verdict_parts", {})
    if parts:
        content.append(Paragraph("The Verdict:", 
                                  ParagraphStyle('section', fontSize=12, textColor=brand)))
        
        verdict_items = [
            ("✓ Strongest Point", parts.get("strongest", ""), '#065F46', '#ECFDF5'),
            ("⚠ Biggest Weakness", parts.get("weakness", ""), '#92400E', '#FFFBEB'),
            ("→ Before Next Pitch", parts.get("fix", ""), '#1E3A5F', '#EFF6FF'),
        ]
        
        for label_text, body_text, text_color, bg_color in verdict_items:
            if body_text:
                vt = Table([[
                    Paragraph(label_text, ParagraphStyle('vlabel', fontSize=9,
                                                          textColor=HexColor(text_color))),
                    Paragraph(body_text, ParagraphStyle('vbody', fontSize=10,
                                                         textColor=HexColor(text_color)))
                ]], colWidths=[40*mm, 125*mm])
                vt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor(bg_color)),
                    ('PADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0, white),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                content.append(vt)
                content.append(Spacer(1, 4))
                
    # Black Swan
    if session.get("black_swan"):
        bs = session["black_swan"]
        content.append(Spacer(1, 6))
        content.append(Paragraph("Black Swan Insight", 
                                  ParagraphStyle('section', fontSize=12, textColor=brand, spaceBefore=8, spaceAfter=4)))
        
        finding_text = f"<b>Finding:</b> {bs.get('black_swan_finding', '')}"
        content.append(Paragraph(finding_text, ParagraphStyle('bs_body', fontSize=10, textColor=dark, spaceAfter=4)))
        
        evidence_text = f"<b>Evidence:</b> {bs.get('evidence', '')}"
        content.append(Paragraph(evidence_text, ParagraphStyle('bs_body', fontSize=10, textColor=dark, spaceAfter=6)))
        
        pivots = bs.get('pivots', [])
        if pivots:
            content.append(Paragraph("<b>Potential Pivots:</b>", ParagraphStyle('bs_body', fontSize=10, textColor=dark, spaceAfter=2)))
            for pivot in pivots:
                content.append(Paragraph(f"• {pivot}", ParagraphStyle('bs_bullet', fontSize=10, textColor=dark, leftIndent=10, spaceAfter=2)))
        content.append(Spacer(1, 10))
    
    doc.build(content)
    buffer.seek(0)
    return buffer.read()
