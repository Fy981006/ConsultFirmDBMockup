import os
from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from config import db_file_path

"""if using sqlite3
def create_database(db_file_path):
    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()

    # Location table 
    cursor.execute('''CREATE TABLE IF NOT EXISTS Location
                      (LocationID INTEGER PRIMARY KEY,
                       State TEXT,
                       City TEXT)''')
    # Client table
    cursor.execute('''CREATE TABLE IF NOT EXISTS Client
                      (ClientID INTEGER PRIMARY KEY,
                       ClientName TEXT,
                       LocationID INTEGER,
                       PhoneNumber TEXT,
                       Email TEXT,
                       FOREIGN KEY (LocationID) REFERENCES Location (LocationID))''')

    conn.commit()
    conn.close()
"""
# Using SQL Alchemy
Base = declarative_base()

class Title(Base):
    __tablename__ = 'Title'
    TitleID = Column(Integer, primary_key=True)
    Title = Column(String)

class Consultant(Base):
    __tablename__ = 'Consultant'
    ConsultantID = Column(String, primary_key=True)
    FirstName = Column(String)
    LastName = Column(String)
    Email = Column(String)
    Contact = Column(String)
    PerformanceRating = Column(String)
    TitleHistory = relationship("ConsultantTitleHistory", back_populates="Consultant")

class ConsultantTitleHistory(Base):
    __tablename__ = 'Consultant_Title_History'
    ID = Column(Integer, primary_key=True)
    ConsultantID = Column(String, ForeignKey('Consultant.ConsultantID'))
    TitleID = Column(Integer, ForeignKey('Title.TitleID'))
    StartDate = Column(Date)
    EndDate = Column(Date)
    EventType = Column(String)
    Consultant = relationship("Consultant", back_populates="TitleHistory")
    Title = relationship("Title")

class Location(Base):
    __tablename__ = 'Location'
    LocationID = Column(Integer, primary_key=True)
    State = Column(String)
    City = Column(String)

class Client(Base):
    __tablename__ = 'Client'
    ClientID = Column(Integer, primary_key=True)
    ClientName = Column(String)
    LocationID = Column(Integer, ForeignKey('Location.LocationID'))
    PhoneNumber = Column(String)
    Email = Column(String)
    Location = relationship("Location")

engine = create_engine(f'sqlite:///{db_file_path}')

def create_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

def main():
    create_database()

if __name__ == "__main__":
    main()