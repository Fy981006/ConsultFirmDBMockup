import random
from faker import Faker
from datetime import timedelta, date
from sqlalchemy.orm import sessionmaker # type: ignore
from data_generator.create_db import Consultant, Title, BusinessUnit, ConsultantTitleHistory, engine

def generate_consultant_data(num_titles, start_year, end_year):
    Session = sessionmaker(bind=engine)
    session = Session()

    fake = Faker()
    # Default values for consultant related data
    hiring_season_prob = {
        'Spring': 0.4,
        'Fall': 0.4,
        'Other': 0.2
    }

    attrition_rate = {
        1: 0.03,
        2: 0.02,
        3: 0.01,
        4: 0.01,
        5: 0.01,
        6: 0.01
    }

    performance_rating_dist = {
        'High': 0.2,
        'Average': 0.75,
        'Low': 0.05
    }

    promotion_intervals = {
        'High': {
            1: (1, 2),
            2: (1, 3),
            3: (2, 4),
            4: (1, 3),
            5: (1, 3),
            6: (0, 0)
        },
        'Average': {
            1: (1, 3),
            2: (2, 4),
            3: (3, 5),
            4: (2, 4),
            5: (2, 4),
            6: (0, 0)
        },
        'Low': {
            1: (2, 4),
            2: (3, 5),
            3: (4, 6),
            4: (3, 5),
            5: (3, 5),
            6: (0, 0)
        }
    }

    title_distribution = {
        1: 0.30,
        2: 0.20,
        3: 0.20,
        4: 0.15,
        5: 0.10,
        6: 0.05
    }

    salary_range = {
        1: (60000, 80000),
        2: (80000, 100000),
        3: (100000, 120000),
        4: (120000, 150000),
        5: (150000, 200000),
        6: (200000, 250000)
    }

    # Generate title slots for each year based on the distribution
    num_years = end_year - start_year + 1
    titles_per_year = {year: [] for year in range(start_year, end_year + 1)}

    for title, percentage in title_distribution.items():
        num_title = int(num_titles * percentage)
        for _ in range(num_title):
            year = random.randint(start_year, end_year)
            titles_per_year[year].append(title)

    # Start generating consultants
    consultant_id_counter = 1
    for year in range(start_year, end_year + 1):
        for title_id in titles_per_year[year]:

# Creating Suitable Consultant Pool
            suitable_consultant = None
            for consultant in session.query(Consultant).all():
                current_title_history = session.query(ConsultantTitleHistory).filter_by(ConsultantID=consultant.ConsultantID).order_by(ConsultantTitleHistory.StartDate.desc()).first()
                if current_title_history:
                    current_title_id = current_title_history.TitleID
                    if current_title_id == title_id:
                        continue
                    if current_title_id == 6 or title_id != current_title_id + 1:
                        continue
                    last_promotion_date = current_title_history.StartDate
                    performance_rating = consultant.PerformanceRating
                    interval_min, interval_max = promotion_intervals[performance_rating][current_title_id]
                    years_since_last_promotion = (date(year, 1, 1) - last_promotion_date).days // 365
                    if interval_min <= years_since_last_promotion <= interval_max and current_title_history.EventType != 'Attrition':
                        suitable_consultant = consultant
                        break

            if suitable_consultant:
                consultant_id = suitable_consultant.ConsultantID
                current_title_history = session.query(ConsultantTitleHistory).filter_by(ConsultantID=consultant_id).order_by(ConsultantTitleHistory.StartDate.desc()).first()
                current_title_id = current_title_history.TitleID

# Add Attrition Entry
                if random.random() < attrition_rate[current_title_id]:
                    end_date = date(year, 1, 1) + timedelta(days=random.randint(0, 364))
                    title_history = ConsultantTitleHistory(ConsultantID=consultant_id, TitleID=current_title_id, StartDate=end_date, EndDate=end_date, EventType='Attrition', Salary=current_title_history.Salary)
                    session.add(title_history)
                    continue

                # Add end date to the previous title record
                current_title_history.EndDate = date(year, 1, 1) + timedelta(days=random.randint(0, 364))
                session.add(current_title_history)

# Add Promotion Entry
                start_date = current_title_history.EndDate + timedelta(days=1)
                salary = random.randint(salary_range[title_id][0], salary_range[title_id][1])
                title_history = ConsultantTitleHistory(ConsultantID=consultant_id, TitleID=title_id, StartDate=start_date, EventType='Promotion', Salary=salary)
                session.add(title_history)
            else:
                # Create a new consultant
                consultant_id = f"C{consultant_id_counter:04d}"
                name = fake.name()
                first_name, last_name = name.split(' ', 1)
                email = f"{first_name[0].lower()}{last_name.lower()}{random.randint(100, 999)}@ise558.com"
                phone = fake.phone_number()
                performance_rating = random.choices(list(performance_rating_dist.keys()), weights=performance_rating_dist.values())[0]

                consultant = Consultant(ConsultantID=consultant_id, FirstName=first_name, LastName=last_name, Email=email, Contact=phone, PerformanceRating=performance_rating)

                # Check for attrition before adding the consultant
                if random.random() < attrition_rate[title_id]:
                    continue

                session.add(consultant)
                consultant_id_counter += 1  # Increment the counter only when consultant is added

# Add Hiring Entry
                hiring_season = random.choices(list(hiring_season_prob.keys()), weights=hiring_season_prob.values())[0]
                if hiring_season == 'Spring':
                    start_date = date(year, random.randint(3, 5), random.randint(1, 30))
                elif hiring_season == 'Fall':
                    start_date = date(year, random.randint(9, 11), random.randint(1, 30))
                else:
                    start_date = date(year, 1, 1) + timedelta(days=random.randint(0, 364))

                salary = random.randint(salary_range[title_id][0], salary_range[title_id][1])
                title_history = ConsultantTitleHistory(ConsultantID=consultant_id, TitleID=title_id, StartDate=start_date, EventType='Hire', Salary=salary)
                session.add(title_history)

    session.commit()
    session.close()

def assign_business_units_to_consultants(business_unit_distribution):
    Session = sessionmaker(bind=engine)
    session = Session()

    business_units = session.query(BusinessUnit).all()
    business_unit_names = [unit.BusinessUnitName for unit in business_units]

    # Check if the provided business unit names in the distribution match the existing business units
    if set(business_unit_distribution.keys()) != set(business_unit_names):
        raise ValueError("The business unit names in the distribution do not match the existing business units.")

    # Normalize the distribution values to ensure they sum up to 1
    total_distribution = sum(business_unit_distribution.values())
    normalized_distribution = {unit: value / total_distribution for unit, value in business_unit_distribution.items()}

    for consultant in session.query(Consultant).all():
        business_unit_name = random.choices(business_unit_names, weights=[normalized_distribution[unit] for unit in business_unit_names])[0]
        business_unit = session.query(BusinessUnit).filter(BusinessUnit.BusinessUnitName == business_unit_name).first()
        consultant.BusinessUnitID = business_unit.BusinessUnitID

    session.commit()
    session.close()
