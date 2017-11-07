#!/usr/bin/env python
"""Create report from features and policies for a set of stories.

Python3 only.

Simeon Warner, 2015-09.., 2017-09..
"""

import sys
import re
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen, Request
from configparser import RawConfigParser
import xml.etree.ElementTree as ElementTree
import getpass
import json
import logging
from optparse import OptionParser, OptionGroup
import html2text
from datetime import datetime, date
import os
import sys

if sys.version_info < (3, 3):
    raise Exception("Must use python 3.3 or greater")

# Global setup
PRIORITY_TO_VALUE = {'Critical': 3, 'Major': 2, 'Low': 1}
VALUE_TO_PRIORITY = dict((v, k) for k, v in PRIORITY_TO_VALUE.items())
PRIORITIES = sorted(PRIORITY_TO_VALUE.keys(), key=lambda x: -
                    PRIORITY_TO_VALUE[x])  # highest first


def html_to_tex(html):
    """Simple wrapper for html2txt with some options and tweak to make TeX."""
    h = html2text.HTML2Text()
    h.body_width = 0  # no wrapping
    txt = h.handle(html).strip()
    # Remove linebreaks
    txt = re.sub(r'[\r\n]', ' ', txt)
    # Deal with some TeX issues
    # http://tex.stackexchange.com/questions/34580/escape-character-in-latex
    txt = re.sub(r'([\&%$#_\{\}])', r'\\\g<1>', txt)
    # Replace markdown links with TeX hyperlinks
    txt = re.sub(r'\[[A-Z]+-\d+\]\([^\)]+/([A-Z]+-\d+)\)',
                 r'\\hyperlink{\g<1>}{\g<1>}',
                 txt)
    # Ditch any trailing period
    txt = re.sub(r'\s*\.\s*$', '', txt)
    return txt


def issue_number(issue):
    """Return issue number extracted from issue['key']."""
    m = re.match(r'[A-Z]+\-(\d+)', issue['key'])
    return(int(m.group(1)) if (m) else 0)


def key_number(key):
    """Return issue number extracted from key."""
    m = re.match(r'[A-Z]+\-(\d+)', key)
    return(int(m.group(1)) if (m) else 0)


def jira_login_cookie(baseuri, username='', password=''):
    """Jira login to get cookie.

    See docs at: https://developer.atlassian.com/jiradev/jira-apis/jira-rest-apis/jira-rest-api-tutorials/jira-rest-api-example-cookie-based-authentication

    Can test loging from command line with

    curl -v -H "Content-type: application/json" --data '{ "username": "XXX", "password": "YYY" }' https://culibrary.atlassian.net/rest/auth/1/session

    expect HTTP 200 and JSON content with:

    {"session":{"name":"cloud.session.token","value":"eyJraWQ..."}}

    where we return the cookie "cloud.session.token=eyJraWQ..."
    """
    if (username is None or username == ''):
        logging.warn("No jira username supplied, will not try to login.")
        return()
    if (password is None or password == ''):
        password = getpass.getpass("No jira password supplied, enter now:")

    auth_uri = urljoin(baseuri, 'rest/auth/1/session')
    logging.warn("Trying Jira login for %s at %s..." % (username, auth_uri))
    auth_data = json.dumps({'username': username, 'password': password}).encode()
    req = Request(auth_uri, auth_data, headers={'Content-type': 'application/json'})
    with urlopen(req) as fh:
        data = json.loads(fh.read().decode())
        if ('session' in data and
                'name' in data['session'] and
                'value' in data['session'] and
                data['session']['name'] == 'cloud.session.token'):
            cookie = data['session']['name'] + '=' + data['session']['value']
            logging.warn("Got Jira login cookie.")
            return(cookie)
        raise Exception("Unexpected response from Jira cookie login")


def query_jira(baseuri, query, username, password, fields=None, options=None):
    """Run query against Jira.

    Extract from Jira 5.2.5 XML response:

    It is possible to restrict the fields that are returned in this document
    by specifying the 'field' parameter in your request. For example, to
    request only the issue key and summary add field=key&field=summary to
    the URL of your request.
    For example:
    https://issues.library.cornell.edu/sr/jira.issueviews:searchrequest-xml/temp/SearchRequest.xml?jqlQuery=project+%3D+ARXIVDEV+AND+resolution+%3D+Unresolved+AND+fixVersion+%3D+%22Roadmap+%28Epics%29%22+ORDER+BY+priority+DESC&tempMax=1000&field=key&field=summary
    """
    cookie = jira_login_cookie(baseuri, username, password)

    params = [('jql', query), ('tempMax', 1000)]
    for field in fields:
        params.append(('field', field))
    query_uri = urljoin(baseuri,
                        'sr/jira.issueviews:searchrequest-xml/temp/SearchRequest.xml?' + urlencode(params))
    if (options.show_uri):
        print(query_uri)
        sys.exit(0)
    req = Request(query_uri, headers={'Cookie': cookie})
    with urlopen(req) as fh:
        xml = fh.read().decode("utf-8")
        if (options.show_xml):
            print(xml)
            sys.exit(0)
        # return parsed etree root element
        return ElementTree.fromstring(xml)  # FIXME - would be better to parse fh but need to decode


relation_translations = {
    'relates to': 'Is related to',
    'is related to': 'Is related to',
    'is relied upon by': 'Is relied upon by',
    'relies on': 'Relies on',
}


def parse_issue_links(key, el):
    """Parse issuelinks in etree element el.

    Ket is just used for debugging information.

    Example XML:
    <issuelinks>
      <issuelinktype id="10061">
        <name>Relation</name>
        <outwardlinks description="relates to">
          <issuelink>
            <issuekey id="67236">IRS-203</issuekey>
          </issuelink>
        </outwardlinks>
      </issuelinktype>
      <issuelinktype id="10062">
        <name>Rely</name>
        <inwardlinks description="is relied upon by">
          <issuelink>
            <issuekey id="66269">IRS-111</issuekey>
          </issuelink>
          <issuelink>
            <issuekey id="66270">IRS-112</issuekey>
          </issuelink>
        </inwardlinks>
      </issuelinktype>
    </issuelinks>
    """
    links = {}
    if (el is None):
        return(links)
    for issuelinktype in el.findall('./issuelinktype'):
        for outwardlink in issuelinktype.findall('./outwardlinks'):
            linktype = outwardlink.attrib['description']
            if (linktype in relation_translations):
                linktype = relation_translations[linktype]
            else:
                logging.warn("%s: Unexpected outward link type: '%s'" % (key, linktype))
            for issuekey in outwardlink.findall('./issuelink/issuekey'):
                # print(issuekey.text)
                if (linktype not in links):
                    links[linktype] = []
                links[linktype].append(issuekey.text)
        for inwardlink in issuelinktype.findall('./inwardlinks'):
            linktype = inwardlink.attrib['description']
            if (linktype in relation_translations):
                linktype = relation_translations[linktype]
            else:
                logging.warn("%s: Unexpected inward link type: '%s'" % (key, linktype))
            for issuekey in inwardlink.findall('./issuelink/issuekey'):
                # print(issuekey.text)
                if (linktype not in links):
                    links[linktype] = []
                links[linktype].append(issuekey.text)
    return(links)


def parse_epic_link(key, el):
    """Extract key of epic this issue belongs to (if given), else ''.

    Example XML:

    <customfields>
      <customfield id="customfield_10730" key="com.pyxis.greenhopper.jira:gh-epic-link">
        <customfieldname>Epic Link</customfieldname>
        <customfieldvalues>
          <customfieldvalue key="$xmlutils.escape($text)">Maintenance</customfieldvalue>
        </customfieldvalues>
      </customfield>
      ...
    </customfields>

    It seems almost certain that the inclusion of `$xmlutils.escape($text)` is a bug in Jira and
    that should instead have the actual epic issue key. [2017-09-12]
    """
    if (el is None):
        return('')
    for customfield in el.findall('./customfield'):
        if (customfield.attrib['id'] == "customfield_10730"):
            field = customfield.find('./customfieldvalues/customfieldvalue')
            if (field.attrib['key'] == '$xmlutils.escape($text)'):
                return field.text  # Use epic name if can't get key (Jira bug!)
            else:
                return field.attrib['key']
    return('')

def parse_timeestimate(key, el):
    """Get work time in days for time estimate.

    Assume that:
       week => 5 days
       day => 1 day
       hour => 1/8 day
       minute => 1/(8*60) day etc.
    """
    m = re.match(r'''^(\d+(\.\d+)?)\s+(\w+)$''', el.text)
    if (m):
        t = float(m.group(1))
        unit = m.group(3).rstrip('s')
        if (unit == 'month'):
            t *= 21.7  # approx work days in month
        elif (unit == 'week'):
            t *= 5
        elif (unit == 'day'):
            pass
        elif (unit == 'hour'):
            t /= 8.0
        elif (unit == 'minute'):
            t /= (8.0 * 60.0)
        elif (unit == 'second'):
            t /= (8.0 * 60.0 * 60.0)
        else:
            logging.warn("Failed to parse time unit '%s' in '%s'" % (unit, el.text))
            return 0.0
        return t
    else:
        logging.warn("Failed to parse time estimate '%s'" % (el.text))
        return 0.0

def split_jira_results(root, fields):
    """Separate results into features, policies and user_stories."""
    issues = ''
    features = []
    policies = []
    user_stories = []
    epics = []
    num = 0
    for item in root.findall('./channel/item'):
        args = {}
        # Try to find key first so we get useful debugging
        key = 'UNKNOWN-KEY'
        for field in (['key'] + fields + ['timeestimate', 'customfields']):
            el = item.find(field)
            if (field == 'issuelinks'):
                args[field] = parse_issue_links(key, el)
            elif (field == 'customfields'):
                # Get epic link if present
                args['epic'] = parse_epic_link(key, el)
            elif (field == 'timeestimate' and el is not None):
                # Get estimate in seconds
                args['days'] = parse_timeestimate(key, el)
            elif (el is None):
                args[field] = 'FIXME - missing %s' % (field)
            elif (el.text is None):
                args[field] = None
            else:
                args[field] = el.text
                if (field == 'key'):
                    key = args['key']
        num += 1
        args['num'] = num
        args['summary'] = html_to_tex(args['summary'])
        if (args['description']):
            args['description'] = html_to_tex(args['description'])
        else:
            args['description'] = args['summary']
        if (not re.search(r'[\?\!\.]$', args['description'])):
            args['description'] += '.'
        args['keytarget'] = "\\hypertarget{%s}{}" % (key)
        args['keyref'] = "\\hyperlink{%s}{%s}" % (key, key)
        # print(key+" --epic--> "+args['epic'])
        # What type is this?
        if (args['type'] == 'New Feature'):
            args['type'] = 'Feature'
            summary = re.sub(r'Feature:\s+', '', args['summary'])
            if (summary == args['summary']):
                raise Exception("%s: is Feature but without summary prefix '%s'" % (key, args['summary']))
            args['summary'] = summary
            if (args['priority'] not in PRIORITIES):
                raise Exception("%s: is Feature with bad priority %s" % (key, args['priority']))
            if ('days' not in args):
                logging.warn("%s: is %s priority Feature without effort estimate" % (key, args['priority']))
            features.append(args)
        elif (args['type'] == 'Policy Question'):
            args['type'] = 'Policy'
            summary = re.sub(r'Policy:\s+', '', args['summary'])
            if (summary == args['summary']):
                raise Exception("%s: is Policy but without summary prefix '%s'" % (key, args['summary']))
            args['summary'] = summary
            if (args['priority'] not in PRIORITIES):
                raise Exception("%s: is Policy with bad priority %s" % (key, args['priority']))
            policies.append(args)
        elif (args['type'] == 'User Story'):
            user_stories.append(args)
            if (args['priority'] not in PRIORITIES):
                raise Exception("%s: is User Story with bad priority %s" % (key, args['priority']))
        elif (args['type'] == 'Epic'):
            epics.append(args)
        else:
            raise Exception("%s: I unexpected type %s" % (key, args['type']))

    return(features, policies, user_stories, epics)


def add_epic_names(issues, epics):
    """Add a field epic_name to each issue.

    If we can't get a name from the supposed key then just use the key
    value as the name.
    """
    for issue in issues:
        if ('epic' in issue):
            epic_key = issue['epic']
            for epic in epics:
                if (epic['key'] == epic_key):
                    issue['epic_name'] = epic['summary']
                    issue['epic_ref'] = '\\hyperlink{%s}{%s}' % (
                        issue['epic_name'], issue['epic_name'])
                    break
            if ('epic_name' not in issue):
                logging.debug("%s: Failed to find epic name for %s (using this)" % (issue['key'], epic_key))
                issue['epic_name'] = epic_key


def add_story_epics(issues, user_stories_by_key):
    """Add a field story_epics to each issue in issues base on the epics its stories rely on."""
    linktype = 'Is relied upon by'
    for issue in issues:
        epic_names = set()
        if (issue['issuelinks'] and linktype in issue['issuelinks']):
            keep = []
            for target in issue['issuelinks'][linktype]:
                if (target in user_stories_by_key):
                    story = user_stories_by_key[target]
                    epic_names.add(story['epic_name'])
                    keep.append(target)
                else:
                    print("Non-story %s linked from %s, link ignored" %
                          (target, issue['key']))
            # replace with the list of keepers
            issue['issuelinks'][linktype] = keep
        issue['issuelinks']['User story groups'] = list(epic_names)


def add_related(issues):
    """Add related field built from issuelink."""
    for issue in issues:
        issue['related'] = ''
        if (issue['issuelinks']):
            for linktype in sorted(issue['issuelinks'].keys()):
                targets = []
                for target in sorted(issue['issuelinks'][linktype], key=key_number):
                    targets.append("\\hyperlink{%s}{%s}" % (target, target))
                issue['related'] += '\n' + linktype + ': ' + ', '.join(targets) + '\n'


def get_issue(issues, target, msg="issues"):
    """Lookup issue based on the key.

    FIXME - This is mindblowingly inefficient! need lookup by key
    """
    for t in (issues):
        if (t['key'] == target):
            return(t)
    raise Exception("Cannot find %s in %s" % (target, msg))


def infer_feature_policy_priorities(user_stories, other, fp, modify=True):
    """Infer feature and policy priorities from user_story priorities.

    The inferred feature or policy priority will be the highest of the priorities
    of the stories that rely upon it. For policies we also look through
    the other issues which will be features and take the highest of these
    priorities. This implies that feature priorities must be inferred
    before policy priorities.


    """
    for issue in fp:
        priority = None
        if ('Is relied upon by' in issue['issuelinks']):
            for target in issue['issuelinks']['Is relied upon by']:
                t = get_issue(user_stories + other, target)
                p = t['priority']
                if (priority is None or PRIORITY_TO_VALUE[p] > PRIORITY_TO_VALUE[priority]):
                    priority = p
        else:
            print("Issue %s is not relied upon by any issue" % (issue['key']))
        if (priority is None):
            print("No priority calculated for %s, treating as Low" %
                  (issue['key']))
            priority = 'Low'
        elif (PRIORITY_TO_VALUE[issue['priority']] < PRIORITY_TO_VALUE[priority]):
            print("INCONSISTENCY: %s has priority %s, which is lower from inferred priority %s" % (
                issue['key'], issue['priority'], priority))
            if (modify):
                print("%s priority changed %s -> %s" %
                      (issue['key'], issue['priority'], priority))
                issue['priority'] = priority
        elif (PRIORITY_TO_VALUE[issue['priority']] > PRIORITY_TO_VALUE[priority]):
            print("%s has priority %s, which is higher than inferred priority %s" % (
                issue['key'], issue['priority'], priority))


def check_story_priorities(features, policies, user_stories, modify=False):
    """Infer story priorities from feature and policy priorities as a sanity check.

    The story priority calculated will be the lowest of the priorities of the
    features and policies it relies upon. An inconsistency warning will be shown
    if the actual story priority is higher than this, a simple note if it is
    lower.

    If modify is true, then instead of showing a warning, the priority will be
    changed. This is a BACKWARDS process, it makes more sense
    to prioritize the user stories and then infer feature and policy
    priorities from that. See infer_feature_policy_priorities().
    """
    for issue in user_stories:
        priority = None
        if ('Relies on' in issue['issuelinks']):
            for target in issue['issuelinks']['Relies on']:
                t = get_issue(features + policies, target)
                p = t['priority']
                if (p is None):
                    raise Exception(
                        "Cannot find %s in features or priorities" % (target))
                if (priority is None or PRIORITY_TO_VALUE[p] < PRIORITY_TO_VALUE[priority]):
                    priority = p
        else:
            print("Issue %s does not rely on any feature or policy" %
                  (issue['key']))
        if (priority is None):
            print("No priority calculated for %s, treating as Low" %
                  (issue['key']))
            priority = 'Low'
        elif (PRIORITY_TO_VALUE[issue['priority']] > PRIORITY_TO_VALUE[priority]):
            print("INCONSISTENCY: %s has priority %s, higher than inferred priority %s" % (
                issue['key'], issue['priority'], priority))
            if (modify):
                print("Setting %s to priority %s" % (issue['key'], priority))
                issue['priority'] = priority
        elif (PRIORITY_TO_VALUE[issue['priority']] < PRIORITY_TO_VALUE[priority]):
            print("%s has priority %s, lower than inferred priority %s" %
                  (issue['key'], issue['priority'], priority))

def add_effort_estimates(features):
    """Loop over all features and add up estimates grouped by priority."""
    num = {}
    totals = {}
    missing = {}
    for issue in features:
        priority = issue['priority']
        if (priority not in totals):
            num[priority] = 0
            totals[priority] = 0.0
            missing[priority] = []
        num[priority] += 1
        if ('days' in issue):
            totals[priority] += issue['days']
        else:
            missing[priority].append(issue['key'])
    for priority in sorted(totals.keys()):
        print("Effort estimate for %d %s features = %.1d work days" % (num[priority], priority, totals[priority]))
        if (len(missing[priority]) > 0):
            print("  (missing estimates for " + ','.join(missing[priority]) + ')')


# Options
#
parser = OptionParser(
    description="Make query to Jira and format results as text message to stdout")
parser.add_option("-u", "--show-uri", dest="show_uri", action="store_true",
                  help="show query URI and exit")
parser.add_option("-s", "--show-xml", dest="show_xml", action="store_true",
                  help="show XML response from Jira and exit")
parser.add_option("-v", "--verbose", action="store_true",
                  help="be verbose")
(options, args) = parser.parse_args()

# Config
#
# Look in current dirs, user home, script install
config = RawConfigParser()
for loc in os.curdir, os.path.expanduser("~"), os.path.dirname(__file__):
    try:
        with open(os.path.join(loc, 'irs_reporter.cfg')) as source:
            config.readfp(source)
        break  # one success is enough
    except IOError:
        pass
#
section = 'irs_reporter'
name = config.get(section, 'name')
username = config.get(section, 'username')
password = config.get(section, 'password')
baseuri = config.get(section, 'baseuri')
# as cut-paste from advanced search box in Jira
query = config.get(section, 'query')
# See
# https://confluence.atlassian.com/jira/displaying-search-results-in-xml-185729644.html
# for a description of fields available
fields = ['key', 'type', 'summary', 'description', 'status',
          'link', 'component', 'priority', 'issuelinks', 'timetracking', 'allcustom']

if (not query):
    raise Exception("No query in config!")

# Get data from Jira
root = query_jira(baseuri, query, username, password, fields, options)
(features, policies, user_stories, epics) = split_jira_results(root, fields)
add_epic_names(user_stories, epics)
user_stories_by_key = {}
for issue in user_stories:
    user_stories_by_key[issue['key']] = issue
add_story_epics(features, user_stories_by_key)
add_story_epics(policies, user_stories_by_key)
add_related(features)
add_related(policies)
add_related(user_stories)

# Adjust feature and policy priorities based on user story priorities
print("\nChecking/inferring feature priorities")
infer_feature_policy_priorities(user_stories, [], features)
print("\nChecking/inferring policy priorities")
infer_feature_policy_priorities(user_stories, features, policies)

# Sanity check than inference the other way works...
print("\nChecking story priorities")
check_story_priorities(features, policies, user_stories)
print("")

print("\nAdding up effort estimates for each priority")
add_effort_estimates(features)
print("")

script_dir = os.path.dirname(__file__)
template_dir = os.path.join(script_dir, 'templates')
template_prefix = 'irs_'

# Use standard templates ala
# http://docs.python.org/2/library/string.html#format-examples
wrapper_template = open(os.path.join(template_dir, template_prefix + "wrapper.tpl")).read()

# Now wrap issues
wrapper_args = {'name': name,
                'now': str(datetime.now()),
                'date': str(date.today()),
                'query': query,
                'program': os.path.basename(__file__)}


feature_template = """{keytarget}
\subsubsection{{Feature: {summary} ({key}, {priority})}}

{description}
{related}

"""
features_txt = ''
for priority in PRIORITIES:
    features_txt += "\subsection{{%s priority features}}\n\n" % (priority)
    for issue in sorted(features, key=issue_number):
        if (issue['priority'] == priority):
            features_txt += feature_template.format(**issue)

policy_template = """{keytarget}
\subsubsection{{Policy: {summary} ({key}, {priority})}}

{description}
{related}

"""
policies_txt = ''
for priority in PRIORITIES:
    policies_txt += "\subsection{{%s priority policies}}\n\n" % (priority)
    for issue in sorted(policies, key=issue_number):
        if (issue['priority'] == priority):
            policies_txt += policy_template.format(**issue)


user_stories_template = """{keytarget}
\subsubsection{{User story: {description} ({key}, {epic_name}, {priority})}}

{related}

"""
user_stories_txt = ''
epic_names = set()
for issue in user_stories:
    epic_names.add(issue['epic_name'])
for epic_name in sorted(epic_names):
    user_stories_txt += "\\hypertarget{%s}{}\n\subsection{%s}\n\n" % (epic_name, epic_name)
    for issue in sorted(user_stories, key=lambda i: ((4 - PRIORITY_TO_VALUE[i['priority']]) * 10000 + issue_number(i))):
        if (issue['epic_name'] == epic_name):
            if (issue['related'] == ''):
                issue['related'] = "\\textit{No features or policies have been associated with this user story.}\n"
            user_stories_txt += user_stories_template.format(**issue)


txt = wrapper_template.format(features=features_txt,
                              policies=policies_txt,
                              user_stories=user_stories_txt,
                              **wrapper_args)

filename = template_prefix + 'report.tex'
fh = open(filename, 'w')
fh.write(txt)
fh.close()
print("Written %s, done." % (filename))
