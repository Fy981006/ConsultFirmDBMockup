import random
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from .create_db import Consultant, ConsultantTitleHistory, Payroll, engine

def generate_payroll():
    Session = sessionmaker(bind=engine)
    session = Session()

    consultants = session.query(Consultant).all()
    all_payroll_records = []

    for consultant in consultants:
        title_history = session.query(ConsultantTitleHistory).filter_by(ConsultantID=consultant.ConsultantID).order_by(ConsultantTitleHistory.StartDate).all()

        for i in range(len(title_history)):
            start_date = title_history[i].StartDate
            end_date = title_history[i].EndDate if title_history[i].EndDate else date.today()

            base_salary = title_history[i].Salary
            monthly_base = base_salary / 12  # Monthly base salary

            current_date = start_date
            while current_date <= end_date:
                payroll_amount = monthly_base

                variation_percentage = random.uniform(-0.05, 0.05)
                payroll_amount += payroll_amount * variation_percentage
                payroll_amount = round(payroll_amount, 2)

                payroll = Payroll(ConsultantID=consultant.ConsultantID, Amount=payroll_amount, EffectiveDate=current_date)
                all_payroll_records.append(payroll)

                current_date += relativedelta(months=1)
                if current_date > end_date:
                    break

    # Sort all payroll records by date
    all_payroll_records.sort(key=lambda x: x.EffectiveDate)

    # Add sorted records to the session
    for record in all_payroll_records:
        session.add(record)

    session.commit()
    session.close()

def main():
    print("Generating Payroll Data...")
    generate_payroll()
    print("Complete")

if __name__ == "__main__":
    main()