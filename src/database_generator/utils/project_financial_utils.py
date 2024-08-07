import random
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from sqlalchemy import func, cast, Integer
from sqlalchemy.orm import aliased
from models.db_model import *
from config import project_settings

def round_to_nearest_thousand(value):
    return Decimal(value).quantize(Decimal('1000'), rounding=ROUND_HALF_UP)

def calculate_hourly_cost(session, consultant_id, year):
    avg_salary = session.query(func.avg(ConsultantTitleHistory.Salary)).filter(
        ConsultantTitleHistory.ConsultantID == consultant_id,
        func.extract('year', ConsultantTitleHistory.StartDate) == year
    ).scalar()
    if avg_salary is None:
        logging.warning(f"No salary data found for consultant {consultant_id} in year {year}. Using fallback method.")
    hourly_cost = (avg_salary / 12) / (52 * 40)  # Assuming 52 weeks and 40 hours per week
    return hourly_cost * (1 + project_settings.OVERHEAD_PERCENTAGE)

def calculate_average_experience(session, title_id, current_date):
    ConsultantCustomDataAlias = aliased(ConsultantCustomData)
    
    consultants = session.query(Consultant).join(
        ConsultantCustomDataAlias,
        Consultant.ConsultantID == ConsultantCustomDataAlias.ConsultantID
    ).filter(
        cast(func.json_extract(ConsultantCustomDataAlias.CustomData, '$.title_id'), Integer) == title_id
    ).all()
    
    if not consultants:
        return 5  # Default to 5 years if no consultants found for this title
    
    total_experience = sum((current_date.year - c.HireYear) for c in consultants)
    return total_experience / len(consultants)

def calculate_project_financials(session, project, assigned_consultants, current_date, deliverables):
    # Calculate billing rates for each title
    title_billing_rates = {}
    for consultant in assigned_consultants:
        consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
        title_id = consultant_custom_data.CustomData.get('title_id', 1)
        if title_id not in title_billing_rates:
            title_billing_rates[title_id] = calculate_billing_rate(
                title_id, 
                project.Type, 
                current_date.year - consultant.HireYear
            )

    # Calculate estimated total cost and revenue from consultant hours
    estimated_total_cost = Decimal('0')
    estimated_total_revenue = Decimal('0')
    for consultant in assigned_consultants:
        consultant_hours = Decimal(project.PlannedHours) / Decimal(len(assigned_consultants))
        cost_rate = Decimal(str(calculate_hourly_cost(session, consultant.ConsultantID, current_date.year)))
        consultant_custom_data = session.query(ConsultantCustomData).get(consultant.ConsultantID)
        billing_rate = title_billing_rates[consultant_custom_data.CustomData.get('title_id', 1)]
        
        estimated_total_cost += cost_rate * consultant_hours
        estimated_total_revenue += billing_rate * consultant_hours

    # Generate predefined expenses
    predefined_expenses = generate_predefined_expenses(project, float(estimated_total_cost), deliverables)

    # Update estimated total cost and revenue with predefined expenses
    expense_total_cost = Decimal('0')
    expense_total_revenue = Decimal('0')
    for expense in predefined_expenses:
        expense_total_cost += Decimal(str(expense['Amount']))
        if expense['IsBillable']:
            expense_total_revenue += Decimal(str(expense['Amount']))

    estimated_total_cost += expense_total_cost
    estimated_total_revenue += expense_total_revenue

    if project.Type == 'Fixed':
        project.Price = float(round_to_nearest_thousand(estimated_total_revenue))
    else:  # Time and Material
        project.EstimatedBudget = float(round_to_nearest_thousand(estimated_total_revenue))
        
        # Generate Project Billing Rates
        billing_rates = []
        for title_id, rate in title_billing_rates.items():
            billing_rates.append(ProjectBillingRate(
                ProjectID=project.ProjectID,
                TitleID=title_id,
                Rate=float(rate)
            ))
        
        session.add_all(billing_rates)
        session.flush()

    # Distribute price to deliverables for fixed contracts
    if project.Type == 'Fixed':
        total_planned_hours = Decimal(sum(d.PlannedHours for d in deliverables))
        for deliverable in deliverables:
            deliverable.Price = float((Decimal(project.Price) * (Decimal(deliverable.PlannedHours) / total_planned_hours)).quantize(Decimal('0.01')))

    session.flush()
    logging.info(f"Calculated financials for project {project.ProjectID}. Estimated total cost: {estimated_total_cost}, Estimated total revenue: {estimated_total_revenue}, Predefined expenses: {len(predefined_expenses)}")

    return estimated_total_cost, estimated_total_revenue, predefined_expenses

def calculate_billing_rate(title_id, project_type, years_experience):
    base_min, base_max = project_settings.HOURLY_RATE_RANGES[title_id]
    
    # Adjust for experience
    experience_factor = Decimal(min(years_experience / 10, 1))  # Cap at 10 years for this calculation
    rate_range = Decimal(base_max - base_min)
    rate = Decimal(base_min) + (rate_range * experience_factor)
    
    # Adjust for project type
    if project_type == 'Fixed':
        rate *= Decimal('0.9')  # Slight discount for fixed-price projects
    
    # Add some randomness
    rate *= Decimal(random.uniform(0.95, 1.05))
    
    return rate.quantize(Decimal('0.01'))
         
def generate_predefined_expenses(project, estimated_total_cost, deliverables):
    expenses = []
    total_planned_hours = sum(d.PlannedHours for d in deliverables)
    project_duration = (project.PlannedEndDate - project.PlannedStartDate).days
    
    for deliverable in deliverables:
        deliverable_cost_ratio = deliverable.PlannedHours / total_planned_hours
        deliverable_estimated_cost = Decimal(str(estimated_total_cost)) * Decimal(str(deliverable_cost_ratio))

        for category, details in project_settings.EXPENSE_CATEGORIES.items():
            min_range, max_range = details['range']
            
            # Calculate the target total for this category based on the percentage
            target_total = deliverable_estimated_cost * Decimal(str(details['percentage']))
            
            # Ensure the target total is within the specified range
            category_total = Decimal(str(max(min_range, min(float(target_total), max_range))))
            
            # Determine the number of expense entries for this category
            num_entries = random.randint(1, 5)  # Generate between 1 to 5 entries per category
            
            remaining_total = category_total
            for i in range(num_entries):
                # Generate a random date within the project timeline
                days_offset = random.randint(0, project_duration)
                expense_date = project.PlannedStartDate + timedelta(days=days_offset)
                
                # Ensure the expense date doesn't exceed the project's actual end date
                if project.ActualEndDate and expense_date > project.ActualEndDate:
                    expense_date = project.ActualEndDate
                
                # Calculate the amount for this entry
                if i == num_entries - 1:  # Last entry
                    amount = remaining_total
                else:
                    amount = remaining_total * Decimal(str(random.uniform(0.1, 0.5)))
                amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                remaining_total -= amount
                
                if amount > Decimal('0'):
                    expense = {
                        'DeliverableID': deliverable.DeliverableID,
                        'Amount': float(amount),
                        'Description': f"{category} expense for {deliverable.Name}",
                        'Category': category,
                        'IsBillable': details['billable'],
                        'Date': expense_date.isoformat()  # Convert date to string
                    }
                    expenses.append(expense)

    logging.info(f"Generated {len(expenses)} predefined expenses for project {project.ProjectID}")
    return expenses

def generate_expense_records(session, project, current_date):
    project_custom_data = session.query(ProjectCustomData).filter_by(ProjectID=project.ProjectID).first()
    if not project_custom_data:
        logging.warning(f"No custom data found for project {project.ProjectID}")
        return

    predefined_expenses = project_custom_data.CustomData.get('predefined_expenses', [])
    if not predefined_expenses:
        logging.warning(f"No predefined expenses found for project {project.ProjectID}")
        return

    # Filter expenses for the current date
    current_expenses = [
        e for e in predefined_expenses 
        if datetime.strptime(e['Date'], '%Y-%m-%d').date() == current_date
    ]

    for expense in current_expenses:
        expense_record = ProjectExpense(
            ProjectID=project.ProjectID,
            DeliverableID=expense['DeliverableID'],
            Date=current_date,
            Amount=float(expense['Amount']),
            Description=expense['Description'],
            Category=expense['Category'],
            IsBillable=expense['IsBillable']
        )
        session.add(expense_record)
        logging.info(f"Generated expense record for project {project.ProjectID}, deliverable {expense['DeliverableID']}: Amount={expense_record.Amount}, Category={expense_record.Category}")

    session.flush()
    logging.info(f"Generated {len(current_expenses)} expense records for project {project.ProjectID} on {current_date}")
