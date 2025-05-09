# schedule_app/core/exporter.py

import os
import json
import logging
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from .config import DIRS, db
from .parser import format_time_ampm, time_to_hour
from .data import save_schedule
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import smtplib

# Setup logging
logger = logging.getLogger(__name__)

def create_schedule_image(workplace, schedule):
    """Create a PNG image of the schedule and save locally and to Firestore"""
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
    
    # Also store reference in Firestore if available
    if db is not None:
        try:
            storage_ref = {
                'type': 'image',
                'local_path': path,
                'created_at': datetime.now().isoformat(),
                'format': 'png'
            }
            
            # Store metadata about the file
            db.collection('workplaces').document(workplace).collection('exports').add(storage_ref)
            logger.info(f"Stored image reference in Firestore for {workplace}")
        except Exception as e:
            logger.error(f"Error storing image reference in Firestore: {str(e)}")
            
    return path

def create_schedule_csv(workplace, schedule):
    """Create a CSV file of the schedule and save locally and to Firestore"""
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
    
    # Also store reference in Firestore if available
    if db is not None:
        try:
            storage_ref = {
                'type': 'csv',
                'local_path': path,
                'created_at': datetime.now().isoformat(),
                'format': 'csv'
            }
            
            # Store metadata about the file
            db.collection('workplaces').document(workplace).collection('exports').add(storage_ref)
            logger.info(f"Stored CSV reference in Firestore for {workplace}")
        except Exception as e:
            logger.error(f"Error storing CSV reference in Firestore: {str(e)}")
            
    return path

def create_schedule_excel(workplace, schedule):
    """Create an Excel file of the schedule and save locally and to Firestore"""
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
    
    # Also store reference in Firestore if available
    if db is not None:
        try:
            storage_ref = {
                'type': 'excel',
                'local_path': path,
                'created_at': datetime.now().isoformat(),
                'format': 'xlsx'
            }
            
            # Store metadata about the file
            db.collection('workplaces').document(workplace).collection('exports').add(storage_ref)
            logger.info(f"Stored Excel reference in Firestore for {workplace}")
        except Exception as e:
            logger.error(f"Error storing Excel reference in Firestore: {str(e)}")
            
    return path

def save_schedule_to_firestore(workplace, schedule, metadata=None):
    """Save the schedule directly to Firestore"""
    if db is None:
        logger.error("Firebase not initialized")
        return False
    
    try:
        # Create schedule data structure
        schedule_data = {
            'schedule': schedule,
            'created_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        # Save to Firestore
        success, schedule_id = save_schedule(workplace, schedule_data)
        
        if success:
            logger.info(f"Schedule saved to Firestore for {workplace} with ID {schedule_id}")
            return True
        else:
            logger.error("Failed to save schedule to Firestore")
            return False
    except Exception as e:
        logger.error(f"Error saving schedule to Firestore: {str(e)}")
        return False

def send_schedule_email(workplace, schedule, recipient_emails, sender_email, sender_password):
    """Send schedule via email with attachments"""
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
            
        # Log email sent in Firestore
        if db is not None:
            try:
                email_log = {
                    'recipients': recipient_emails,
                    'sent_at': datetime.now().isoformat(),
                    'success': True
                }
                db.collection('workplaces').document(workplace).collection('email_logs').add(email_log)
            except Exception as e:
                logger.error(f"Error logging email in Firestore: {str(e)}")

        return True, "Email sent successfully"
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        
        # Log failed email in Firestore
        if db is not None:
            try:
                email_log = {
                    'recipients': recipient_emails,
                    'sent_at': datetime.now().isoformat(),
                    'success': False,
                    'error': str(e)
                }
                db.collection('workplaces').document(workplace).collection('email_logs').add(email_log)
            except Exception as log_error:
                logger.error(f"Error logging email failure in Firestore: {str(log_error)}")
                
        return False, str(e)