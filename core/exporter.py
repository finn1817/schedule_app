# schedule_app/core/exporter.py

import os
import json
import logging
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from .config import DIRS
from .parser import format_time_ampm, time_to_hour
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import smtplib

def create_schedule_image(workplace, schedule):
    rows = []
    for day, shifts in schedule.items():
        for s in shifts:
            rows.append({
                "Day": day,
                "Start": s['start'],
                "End": s['end'],
                "Assigned": ", ".join(s['assigned'])
            })
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(10, len(rows) * 0.4))
    ax.axis('off')
    table_data = [["Day","Start","End","Assigned"]] + [
        [r["Day"], format_time_ampm(r["Start"]), format_time_ampm(r["End"]), r["Assigned"]]
        for r in rows
    ]
    table = ax.table(cellText=table_data, cellLoc='center', loc='center')
    for cell in table.get_celld().values():
        cell.set_fontsize(10)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DIRS['schedules'], f"{workplace}_{timestamp}.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path

def create_schedule_csv(workplace, schedule):
    rows = []
    for day, shifts in schedule.items():
        for s in shifts:
            rows.append({
                "Day": day,
                "Start": format_time_ampm(s['start']),
                "End": format_time_ampm(s['end']),
                "Assigned": ", ".join(s['assigned'])
            })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DIRS['schedules'], f"{workplace}_{timestamp}.csv")
    df.to_csv(path, index=False)
    return path

def create_schedule_excel(workplace, schedule):
    dfs = {}
    for day, shifts in schedule.items():
        if shifts:
            dfs[day] = pd.DataFrame([
                {"Start": format_time_ampm(s['start']),
                 "End": format_time_ampm(s['end']),
                 "Assigned": ", ".join(s['assigned'])}
                for s in shifts
            ])
    if not dfs:
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DIRS['schedules'], f"{workplace}_{timestamp}.xlsx")
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for day, df in dfs.items():
            df.to_excel(writer, sheet_name=day, index=False)
        # summary
        all_rows = []
        for day, shifts in schedule.items():
            for s in shifts:
                all_rows.append({
                    "Day": day,
                    "Start": format_time_ampm(s['start']),
                    "End": format_time_ampm(s['end']),
                    "Assigned": ", ".join(s['assigned'])
                })
        if all_rows:
            pd.DataFrame(all_rows).to_excel(writer, sheet_name="Full Schedule", index=False)
    return path

def send_schedule_email(workplace, schedule, recipient_emails, sender_email, sender_password):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(recipient_emails)
        msg['Subject'] = f"{workplace.replace('_',' ').title()} Schedule"

        # HTML body
        html = f"""<html><body><h2>{workplace.replace('_',' ').title()} Schedule</h2>"""
        for day, shifts in schedule.items():
            if shifts:
                html += f"<h3>{day}</h3><table border='1'><tr><th>Start</th><th>End</th><th>Assigned</th></tr>"
                for s in shifts:
                    cls = ' style="color:red;"' if "Unfilled" in s['assigned'] else ""
                    html += (
                        f"<tr><td>{format_time_ampm(s['start'])}</td>"
                        f"<td>{format_time_ampm(s['end'])}</td>"
                        f"<td{cls}>{', '.join(s['assigned'])}</td></tr>"
                    )
                html += "</table>"
        html += "</body></html>"
        msg.attach(MIMEText(html, 'html'))

        # attachments
        for fn in (create_schedule_image, create_schedule_csv, create_schedule_excel):
            path = fn(workplace, schedule)
            if path and os.path.exists(path):
                with open(path, 'rb') as f:
                    subtype = os.path.splitext(path)[1].lstrip('.')
                    part = MIMEApplication(f.read(), _subtype=subtype)
                    part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                    msg.attach(part)

        # send
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return True, "Email sent successfully"
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return False, str(e)
