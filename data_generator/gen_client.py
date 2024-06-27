from sqlalchemy.orm import sessionmaker # type: ignore
from data_generator.create_db import Client, Location, engine
from faker import Faker
import random

def generate_client(num_clients):
    Session = sessionmaker(bind=engine)
    session = Session()

    fake = Faker('en_US')
    client_data = []

    locations = session.query(Location).all()

    regions = {
        'North America': 0.6,
        'EMEA': 0.2,
        'Central and South America': 0.1,
        'Asia Pacific': 0.1
    }

    region_locations = {
        'North America': [location for location in locations if location.State in ['California', 'New York', 'Illinois', 'Texas', 'Pennsylvania', 'Arizona']],
        'EMEA': [location for location in locations if location.State in ['England', 'France', 'Germany', 'Spain', 'Italy', 'Netherlands', 'Russia', 'Sweden', 'Poland', 'Austria']],
        'Central and South America': [location for location in locations if location.State in ['Brazil', 'Mexico', 'Argentina', 'Colombia', 'Peru', 'Venezuela', 'Chile', 'Ecuador', 'Guatemala', 'Cuba']],
        'Asia Pacific': [location for location in locations if location.State in ['China', 'Japan', 'India', 'South Korea', 'Australia', 'Indonesia', 'Philippines', 'Thailand', 'Malaysia', 'Vietnam']]
    }

    for region, percentage in regions.items():
        count = int(num_clients * percentage)
        for _ in range(count):
            location = random.choice(region_locations[region])
            client = Client(
                ClientName=f"{fake.word().capitalize()} {fake.company_suffix()}",
                LocationID=location.LocationID,
                PhoneNumber=fake.phone_number(),
                Email=fake.email()
            )
            client_data.append(client)

    session.add_all(client_data)
    session.commit()
    session.close()

def main(num_clients):
    print("Gnerating Client Data...")
    generate_client(num_clients)
    print("Complete")