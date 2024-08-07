from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
import random
from datetime import timedelta, date
from sqlalchemy import func, case
from collections import Counter
from models.db_model import *
from config import project_settings
import math
import logging

def serialize_dates(data):
    if isinstance(data, dict):
        return {key: serialize_dates(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [serialize_dates(item) for item in data]
    elif isinstance(data, date):
        return data.isoformat()
    else:
        return data
    
def calculate_planned_hours(project, team_size):
    duration_days = (project.PlannedEndDate - project.PlannedStartDate).days
    working_days = math.ceil(duration_days * 5 / 7)  # Assuming 5 working days per week
    
    daily_team_hours = team_size * project_settings.AVERAGE_WORKING_HOURS_PER_DAY
    total_planned_hours = working_days * daily_team_hours
    
    return round(total_planned_hours)

def calculate_target_hours(planned_hours):
    if random.random() < 0.05:  # 10% chance of finishing early
        factor = random.uniform(0.9, 0.95)
    else:  # 95% chance of overrunning
        factor = random.uniform(1.05, 1.1)
    return round(planned_hours * factor)


def assign_project_team(session, project, assigned_consultants):
    '''
    takes the already selected consultants and 
    assigns roles to them in the ProjectTeam table
    '''
    project_manager = assigned_consultants[0]
    
    # Assign Project Manager
    team_member = ProjectTeam(
        ProjectID=project.ProjectID,
        ConsultantID=project_manager.ConsultantID,
        Role='Project Manager',
        StartDate=project.ActualStartDate,
        EndDate=None
    )
    session.add(team_member)
    pm_custom_data = session.query(ConsultantCustomData).get(project_manager.ConsultantID)
    # Sort remaining consultants by title_id in descending order
    team_members = sorted(assigned_consultants[1:], key=lambda c: session.query(ConsultantCustomData).get(c.ConsultantID).CustomData.get('title_id', 1), reverse=True)

    # Assign Team Leads (up to 3 consultants with title_id >= 3)
    team_leads_count = 0
    for consultant in team_members:
        consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
        if consultant_custom_data.CustomData.get('title_id', 1) >= 3 and team_leads_count < 3:
            role = 'Team Lead'
            team_leads_count += 1
        else:
            role = 'Team Member'

        team_member = ProjectTeam(
            ProjectID=project.ProjectID,
            ConsultantID=consultant.ConsultantID,
            Role=role,
            StartDate=project.ActualStartDate,
            EndDate=None
        )
        session.add(team_member)
    session.flush()

def calculate_project_progress(project, deliverables):
    total_planned_hours = sum(d.PlannedHours for d in deliverables)
    
    if total_planned_hours == 0:
        project.Progress = 0
        return

    weighted_progress = sum((d.ActualHours / d.PlannedHours) * (d.PlannedHours / total_planned_hours) * 100 for d in deliverables)
    project.Progress = min(100, int(round(weighted_progress)))



def get_available_consultants(session, current_date):
    two_months_ago = current_date - timedelta(days=60)
    
    # Subquery to get the most recent title for each consultant
    latest_title = session.query(
        ConsultantTitleHistory.ConsultantID,
        func.max(ConsultantTitleHistory.StartDate).label('latest_start_date')
    ).filter(
        ConsultantTitleHistory.StartDate <= current_date
    ).group_by(ConsultantTitleHistory.ConsultantID).subquery()

    results = session.query(
        Consultant,
        ConsultantTitleHistory.TitleID,
        func.coalesce(func.max(ProjectTeam.EndDate), func.min(ConsultantTitleHistory.StartDate)).label('last_project_date'),
        func.count(case((ProjectTeam.EndDate.is_(None) | (ProjectTeam.EndDate >= current_date), 1))).label('active_project_count')
    ).join(
        latest_title,
        Consultant.ConsultantID == latest_title.c.ConsultantID
    ).join(
        ConsultantTitleHistory,
        (Consultant.ConsultantID == ConsultantTitleHistory.ConsultantID) &
        (ConsultantTitleHistory.StartDate == latest_title.c.latest_start_date)
    ).outerjoin(
        ProjectTeam,
        (Consultant.ConsultantID == ProjectTeam.ConsultantID) &
        (ProjectTeam.StartDate <= current_date) &
        ((ProjectTeam.EndDate.is_(None)) | (ProjectTeam.EndDate >= two_months_ago))
    ).filter(
        Consultant.HireYear <= current_date.year 
    ).group_by(
        Consultant.ConsultantID,
        ConsultantTitleHistory.TitleID
    ).order_by(
        'active_project_count',
        'last_project_date'
    ).all()

    available_consultants = []
    for consultant, title_id, last_project_date, active_project_count in results:
        consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
        if not consultant_custom_data:
            consultant_custom_data = ConsultantCustomData(ConsultantID=consultant.ConsultantID, CustomData={})
            session.add(consultant_custom_data)
        
        # Update consultant metadata
        consultant_custom_data.CustomData.update({
            'title_id': title_id,
            'last_project_date': last_project_date.isoformat() if last_project_date else None,
            'active_project_count': int(active_project_count) if active_project_count is not None else 0
        })
        available_consultants.append(consultant)

    return available_consultants


def assign_project_to_business_unit(session, assigned_consultants, active_units, current_year):
    consultant_unit_counts = Counter(consultant.BusinessUnitID for consultant in assigned_consultants)
    project_counts = dict(session.query(
        Project.UnitID, func.count(Project.ProjectID)
    ).filter(
        func.extract('year', Project.PlannedStartDate) == current_year,
        Project.UnitID.in_([unit.BusinessUnitID for unit in active_units])
    ).group_by(Project.UnitID).all())
    
    for unit in active_units:
        if unit.BusinessUnitID not in project_counts:
            project_counts[unit.BusinessUnitID] = 0
    
    total_consultants = sum(consultant_unit_counts.values())
    target_distribution = {unit.BusinessUnitID: consultant_unit_counts.get(unit.BusinessUnitID, 0) / total_consultants 
                           for unit in active_units}
    
    total_projects = sum(project_counts.values())
    current_distribution = {unit_id: count / (total_projects + 1)
                            for unit_id, count in project_counts.items()}
    
    distribution_difference = {unit_id: target_distribution.get(unit_id, 0) - current_distribution.get(unit_id, 0)
                               for unit_id in project_counts.keys()}
    return max(distribution_difference, key=distribution_difference.get)

def assign_consultants_to_project(session, available_consultants, project_manager, target_team_size, current_date):
    '''
    main function to select which consultants will be on the project team.
    '''
    assigned_consultants = [project_manager]
    
    # Separate consultants by title
    consultants_by_title = {title: [] for title in range(1, 7)}
    for c in available_consultants:
        if c != project_manager and c.HireYear <= current_date.year:
            consultant_custom_data = session.query(ConsultantCustomData).get(c.ConsultantID)
            title = consultant_custom_data.CustomData.get('title_id', 1)
            consultants_by_title[title].append(c)

    # Sort consultants in each title group
    for title in consultants_by_title:
        consultants_by_title[title].sort(key=lambda c: session.query(ConsultantCustomData).get(c.ConsultantID).CustomData.get('active_project_count', 0))

    remaining_slots = max(0, target_team_size - 1)  # Subtract 1 for the project manager

    # Calculate target counts for each title
    target_counts = {title: max(1, round(remaining_slots * project_settings.TITLE_DISTRIBUTION_TARGETS[title])) 
                     for title in range(1, 7)}

    # Adjust target counts to match remaining slots
    while sum(target_counts.values()) > remaining_slots:
        max_title = max(target_counts, key=target_counts.get)
        if target_counts[max_title] > 1:
            target_counts[max_title] -= 1
        else:
            break

    # Assign consultants based on target counts
    for title in range(1, 7):
        for _ in range(target_counts[title]):
            if consultants_by_title[title]:
                consultant = consultants_by_title[title].pop(0)
                assigned_consultants.append(consultant)
                remaining_slots -= 1
            else:
                break
    return assigned_consultants, remaining_slots

def set_project_dates(project, current_date, project_manager, session, simulation_start_date):
    # Define duration ranges and their probabilities
    duration_ranges = project_settings.PROJECT_DURATION_RANGE

    # Select a duration range based on the given probabilities
    selected_range, _ = random.choices(duration_ranges, weights=[p for _, p in duration_ranges])[0]

    # Select a specific duration within the chosen range
    duration_months = random.randint(*selected_range)

    pm_availability = max(get_consultant_availability(session, project_manager.ConsultantID, current_date), simulation_start_date)

    # Maintain variance between PlannedStartDate and ActualStartDate
    project.PlannedStartDate = pm_availability + timedelta(days=random.randint(0, 14))
    actual_start_variance = timedelta(days=random.randint(0, 7))
    project.ActualStartDate = project.PlannedStartDate + actual_start_variance

    # Set initial status
    project.Status = 'Not Started'

    # Calculate end date based on working days
    working_days = duration_months * 21  # Assuming 21 working days per month
    project.PlannedEndDate = project.PlannedStartDate
    days_added = 0
    while days_added < working_days:
        project.PlannedEndDate += timedelta(days=1)
        if project.PlannedEndDate.weekday() < 5:  # Monday = 0, Friday = 4
            days_added += 1
    
    if duration_months <= 3:
        target_team_size = random.randint(5, 7)  # Small project
    elif duration_months <= 6:
        target_team_size = random.randint(10, 12)  # Medium project
    else:
        target_team_size = random.randint(12, 15)  # Large project

    return target_team_size

def get_consultant_availability(session, consultant_id, current_date):
    latest_project = session.query(func.max(ProjectTeam.EndDate)).filter(
        ProjectTeam.ConsultantID == consultant_id,
        ProjectTeam.EndDate.isnot(None)
    ).scalar()
    
    return max(current_date, latest_project + timedelta(days=1)) if latest_project else current_date

def generate_deliverables(project, target_hours):
    num_deliverables = random.randint(*project_settings.DELIVERABLE_COUNT_RANGE)
    deliverables = []
    remaining_target_hours = Decimal(str(target_hours))
    project_duration = (project.PlannedEndDate - project.PlannedStartDate).days

    for i in range(num_deliverables):
        is_last_deliverable = (i == num_deliverables - 1)
        
        if is_last_deliverable:
            deliverable_target_hours = remaining_target_hours
        else:
            min_hours = Decimal('10')
            max_hours = max(min_hours, (remaining_target_hours - (num_deliverables - i - 1) * min_hours))
            deliverable_target_hours = Decimal(str(random.uniform(float(min_hours), float(max_hours))))
            remaining_target_hours -= deliverable_target_hours

        start_date = project.PlannedStartDate if i == 0 else deliverables[-1].DueDate + timedelta(days=1)
        deliverable_duration = max(1, int((deliverable_target_hours / Decimal(str(target_hours))) * project_duration))
        due_date = min(start_date + timedelta(days=deliverable_duration), project.PlannedEndDate)

        planned_hours = round_decimal(deliverable_target_hours * (Decimal(str(project.PlannedHours)) / Decimal(str(target_hours))), 1)
        
        deliverable = Deliverable(
            ProjectID=project.ProjectID,
            Name=f"Deliverable {i+1}",
            PlannedStartDate=start_date,
            ActualStartDate=None,  # This will be set when work actually starts on the deliverable
            DueDate=due_date,
            PlannedHours=float(planned_hours),  # Convert to float for database storage
            ActualHours=0.0,
            Progress=0,
            Status='Not Started'
        )
        deliverables.append(deliverable)

    return deliverables

def round_decimal(value, decimal_places=1):
    return value.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)

import random

def update_project_team(session, project, available_consultants, current_team, current_date):
    project_custom_data = session.query(ProjectCustomData).get(project.ProjectID)
    if not project_custom_data:
        project_custom_data = ProjectCustomData(ProjectID=project.ProjectID, CustomData={})
        session.add(project_custom_data)

    target_team_size = project_custom_data.CustomData.get('target_team_size', project_settings.MIN_TEAM_SIZE)
    
    current_team_size = len(current_team)
    remaining_slots = max(0, target_team_size - current_team_size)

    if remaining_slots > 0:
        current_composition = Counter(session.query(ConsultantCustomData).get(c).CustomData.get('title_id', 1) for c in current_team)
        
        target_counts = {title: max(1, round(remaining_slots * project_settings.TITLE_DISTRIBUTION_TARGETS[title])) 
                         for title in range(1, 7)}

        for title in range(1, 7):
            target_counts[title] = max(0, target_counts[title] - current_composition[title])

        # Group available consultants by title
        consultants_by_title = {title: [] for title in range(1, 7)}
        for consultant in available_consultants:
            if consultant.ConsultantID not in current_team:
                consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
                title = consultant_custom_data.CustomData.get('title_id', 1)
                consultants_by_title[title].append(consultant)

        # Sort consultants within each title group
        for title in consultants_by_title:
            consultants_by_title[title].sort(key=lambda c: (
                session.query(ConsultantCustomData).get(c.ConsultantID).CustomData.get('active_project_count', 0),
                random.random()  # Add randomness to the sorting
            ))

        # Iterate through titles in a more balanced way
        titles = list(range(1, 7))
        while remaining_slots > 0 and titles:
            title = random.choice(titles)
            if target_counts[title] > 0 and consultants_by_title[title]:
                consultant = consultants_by_title[title].pop(0)
                consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
                
                if consultant_custom_data.CustomData.get('active_project_count', 0) < project_settings.MAX_PROJECTS_PER_CONSULTANT.get(title, 2):
                    team_member = ProjectTeam(
                        ProjectID=project.ProjectID,
                        ConsultantID=consultant.ConsultantID,
                        Role='Team Member',
                        StartDate=current_date
                    )
                    session.add(team_member)
                    current_team.append(consultant.ConsultantID)
                    consultant_custom_data.CustomData['active_project_count'] = consultant_custom_data.CustomData.get('active_project_count', 0) + 1
                    target_counts[title] -= 1
                    remaining_slots -= 1
                    logging.info(f"Added consultant {consultant.ConsultantID} (Title: {title}) to project {project.ProjectID} team")
            else:
                titles.remove(title)

    project_custom_data.CustomData['team'] = current_team
    project_custom_data.CustomData['remaining_slots'] = remaining_slots
    project_custom_data.CustomData['target_team_size'] = target_team_size