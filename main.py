from src.db_model import main as create_db
from src.database_generator.generators.client import generate_clients
from src.database_generator.generators.location import generate_locations
from src.database_generator.generators.title import generate_titles
from src.database_generator.generators.business_unit import generate_business_units
from src.database_generator.generators.consultant_title_history import main as generate_consultant_title_history
from src.database_generator.generators.payroll import generate_payroll
from src.database_generator.generators.project_deliverable import generate_projects
from src.spreadsheet_generator.indirect_cost import generate_indirect_costs
from src.spreadsheet_generator.non_billable_time import generate_non_billable_time_report

START_YEAR = 2015
END_YEAR = 2016

def main():
    # Initialize DB
    create_db()

    # Generate database
    generate_locations()
    generate_business_units()
    generate_clients(358)
    generate_titles()
    generate_consultant_title_history(initial_num_titles=100, start_year=START_YEAR, end_year=END_YEAR)
    generate_payroll()
    generate_projects(START_YEAR, END_YEAR)
    
    # Generate Spreadsheet
    generate_indirect_costs()

    # Generate non-billable time report
    generate_non_billable_time_report()

    # Generate json file

if __name__ == "__main__":
    main()