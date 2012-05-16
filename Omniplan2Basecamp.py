import csv
import logging
import argparse
import sys
from datetime import datetime
from xml.etree.ElementTree import fromstring
from string import Template
from ConfigParser import SafeConfigParser as ConfigParser

import requests
from requests.auth import HTTPBasicAuth

CONFIG_DEFAULTS_FILENAME = "config.defaults"
CONFIG_FILENAME = "config.local"

BASECAMP_API_PEOPLE_ENDPOINT = Template("projects/$project_id/people.xml")
BASECAMP_API_MILESTONE_ENDPOINT = Template("/projects/$project_id/calendar_entries.xml")

BASECAMP_CALENDAR_TEMPLATE = Template("""<request>
  <calendar-entry>
    <title>$name ###</title>
    <deadline type="date">$date</deadline>
    <type>Milestone</type>
    <responsible-party>$assigned_id</responsible-party>
  </calendar-entry>
</request>""")

def call_api(endpoint, content=None):
    url = BASECAMP_URL + endpoint.substitute(project_id=BASECAMP_PROJECT_ID)
    headers = {"Accept": "application/xml",
            "Content-Type": "application/xml"}
    if not content:
        r = requests.get(url, auth=HTTPBasicAuth(BASECAMP_TOKEN, 'NOTUSED'),
                headers=headers, data=content)
    else:
        r = requests.post(url, auth=HTTPBasicAuth(BASECAMP_TOKEN, 'NOTUSED'),
                headers=headers, data=content)

    logging.warning("Calling URL %s" % url)

    if not (200 <= r.status_code <= 299):
        print r.text
        raise Exception("Error using Basecamp API")

    return r


class Milestone(dict):

    @classmethod
    def from_csv_row(cls, data):
        """Return a new Milestone object from CSV row"""
        conversion = { 
                "Task": "name",
                "Start": "start",
                "Assigned": "assigned",
                "Completed": "completed",
                "End": "date"
                }

        milestone = cls()

        for csv_column, attribute in conversion.items():
            value = data[csv_column]
            if csv_column == "Assigned":
                # get first name
                value = value.decode("utf-8").split(" ")[0]
            if csv_column == "End":
                month, day, year = value.split("/")[:3]
                year = 2000 + int(year.split()[0])
                value = datetime(year, int(month), int(day))
            milestone.__setattr__(attribute, value)

        return milestone

    def update_assigned_with_basecamp_id(self, people_list):
        if not self.assigned:
            self.assigned_id = people_list[DEFAULT_ASSIGNED]
            return

        if not self.assigned in people_list:
            raise Exception("No basecamp id found for %s" % self.assigned)

        self.assigned_id = people_list[self.assigned]

    def write_to_basecamp(self):
        content = BASECAMP_CALENDAR_TEMPLATE.substitute(**self.__dict__)
        r = call_api(BASECAMP_API_MILESTONE_ENDPOINT, content)


class Person(dict):
    @property
    def name(self):
        if USE_ONLY_FIRST_NAME:
            return self.first_name
        else:
            return self.first_name + " " + self.last_name

    @classmethod
    def from_basecamp_xml(cls, xml):
        conversion = {
                "id": "basecamp_id", 
                "first-name": "first_name",
                "last-name":"last_name"}

        person = cls()

        for k, v in conversion.items():
            person.__setattr__(v, xml.find(k).text)

        return person

def get_people_from_basecamp(names=[]):
    r = call_api(BASECAMP_API_PEOPLE_ENDPOINT)
    xml = fromstring(r.text)
    people = {}
    for person_xml in xml.iterfind("person"):
        person = Person.from_basecamp_xml(person_xml)
        people[person.name] = person.basecamp_id

    return people

def main(milestone_file):
    config = ConfigParser()
    config.readfp(open(CONFIG_DEFAULTS_FILENAME))
    config.read(open(CONFIG_FILENAME))

    # 1. Getting the milestones

    milestones = []
    responsibles = set()
    for row in csv.DictReader(milestone_file):
        milestone = Milestone.from_csv_row(row)
        milestones.append(milestone)
        responsibles.add(milestone.assigned)

    # 2. Getting the users and updating milestones

    people_ids = get_people_from_basecamp(responsibles)
    print people_ids
    for m in milestones:
        m.update_assigned_with_basecamp_id(people_ids)

    # 3. Writing to Basecamp
    for m in milestones:
        m.write_to_basecamp()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Write Omnniplan milestones to Basecamp')
    parser.add_argument('csv_file', nargs='?', type=argparse.FileType('r'), 
            default=sys.stdin, help='CSV file exported by Omniplan')
    milestone_file = parser.parse_args().csv_file
    main(milestone_file)
