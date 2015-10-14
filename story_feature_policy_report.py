#!/usr/bin/env python
"""Create report from analysis based on defining a set of features
and policies for a set of stories.

Simeon Warner, 2015-09...
"""

import sys
import re
import urllib
import ConfigParser
import xml.etree.ElementTree as ElementTree
from optparse import OptionParser, OptionGroup
import html2text
from datetime import datetime,date
import os


# Global setup
PRIORITY_TO_VALUE = { 'Critical': 3, 'Major': 2, 'Low': 1 }
VALUE_TO_PRIORITY = dict((v, k) for k, v in PRIORITY_TO_VALUE.iteritems())
PRIORITIES = sorted(PRIORITY_TO_VALUE.keys(), key=lambda x: -PRIORITY_TO_VALUE[x]) #highest first

def html_to_tex(html):
    """Simple wrapper for html2txt with some options and tweak to make TeX."""
    h = html2text.HTML2Text()
    h.body_width = 0 #no wrapping
    txt = h.handle(html).encode('utf-8').strip()
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
    m = re.match(r'[A-Z]+\-(\d+)',issue['key'])
    return( int(m.group(1)) if (m) else 0 )


def key_number(key):
    """Return issue number extracted from key."""
    m = re.match(r'[A-Z]+\-(\d+)',key)
    return( int(m.group(1)) if (m) else 0 )


def query_jira(query,username,password,fields=None,options=None):
    # Extract from Jira 5.2.5 XML response:
    #
    # It is possible to restrict the fields that are returned in this document 
    # by specifying the 'field' parameter in your request. For example, to 
    # request only the issue key and summary add field=key&field=summary to 
    # the URL of your request.
    # For example:
    # https://issues.library.cornell.edu/sr/jira.issueviews:searchrequest-xml/temp/SearchRequest.xml?jqlQuery=project+%3D+ARXIVDEV+AND+resolution+%3D+Unresolved+AND+fixVersion+%3D+%22Roadmap+%28Epics%29%22+ORDER+BY+priority+DESC&tempMax=1000&field=key&field=summary
    
    params = [('jqlQuery',query), ('tempMax', 1000)]
    if (username is not None or password is not None):
        params.append(('os_username', username))
        params.append(('os_password', password))
    for field in fields:
        params.append(('field', field))
        
    uri = "%s/sr/jira.issueviews:searchrequest-xml/temp/SearchRequest.xml?%s" % (baseuri,urllib.urlencode(params))
    if (options.show_uri):
        print(uri)
        sys.exit(0)
    f = urllib.urlopen(uri)
    if (options.show_xml):
        print(f.read())
        sys.exit(0)
    # return parsed etree
    return ElementTree.parse(f)


relation_translations = {
    'relates to': 'Is related to',
    'is related to': 'Is related to',
    'is relied upon by': 'Is relied upon by',
    'relies on': 'Relies on',
}


def parse_issue_links(el):
    """Parse issuelinks in etree element el

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
                raise Exception("Unexpected outward link: %s" % (linktype))
            for issuekey in outwardlink.findall('./issuelink/issuekey'):
                #print(issuekey.text)
                if (linktype not in links):
                    links[linktype]=[]
                links[linktype].append(issuekey.text)
        for inwardlink in issuelinktype.findall('./inwardlinks'):
            linktype = inwardlink.attrib['description']
            if (linktype in relation_translations):
                linktype = relation_translations[linktype]
            else:
                raise Exception("Unexpected inward link: %s" % (linktype))
            for issuekey in inwardlink.findall('./issuelink/issuekey'):
                #print(issuekey.text)
                if (linktype not in links):
                    links[linktype]=[]
                links[linktype].append(issuekey.text)
    return(links)


def parse_epic_link(el):
    """Extract key of epic this issue belongs to (if given), else ''.

    Example XML:
    <customfields>
      <customfield id="customfield_10730" key="com.pyxis.greenhopper.jira:gh-epic-link">
        <customfieldname>Epic Link</customfieldname>
        <customfieldvalues>
          <customfieldvalue>IRS-4</customfieldvalue>
        </customfieldvalues>
      </customfield>
      ...
    </customfields>
    """
    if (el is None):
        return('')
    for customfield in el.findall('./customfield'):
        if (customfield.attrib['id'] == "customfield_10730"):
            return(customfield.find('./customfieldvalues/customfieldvalue').text)
    return('')

    
def split_jira_results(tree, fields):
    """Separate results into features, policies and user_stories"""
    issues = ''
    features = []
    policies = []
    user_stories = []
    epics = []
    root = tree.getroot()
    num = 0
    for item in root.findall('./channel/item'):
        args = {}
        for field in (fields+['customfields']):
            el =item.find(field)
            if (field == 'issuelinks'):
                args[field] = parse_issue_links(el)
            elif (field == 'customfields'):
                # Get epic link if present
                args['epic'] = parse_epic_link(el)
            elif (el is None):
                args[field] = 'FIXME - missing %s' % (field)
            elif (el.text is None):
                args[field] = None
            else:
                args[field] = el.text
        num += 1
        args['num'] = num
        args['summary'] = html_to_tex(args['summary'])
        if (args['description']):
            args['description'] = html_to_tex(args['description'])
        else: 
            args['description'] = args['summary']
        if (not re.search(r'[\?\!\.]$',args['description'])):
            args['description'] += '.'
        key = args['key']
        args['keytarget'] = "\\hypertarget{%s}{}" % (key)
        args['keyref'] = "\\hyperlink{%s}{%s}" % (key,key)
        #print(key+" --epic--> "+args['epic'])
        # What type is this?
        if (args['type'] == 'New Feature'):
            args['type'] = 'Feature'
            summary = re.sub( r'Feature:\s+', '', args['summary'] )
            if (summary == args['summary'] ): 
                raise Exception("%s: is Feature but without summary prefix '%s'" % (key,args['summary']))
            args['summary'] = summary
            if (args['priority'] not in PRIORITIES):
                raise Exception("%s: is Feature with bad priority %s" % (key, args['priority']))
            features.append(args)
        elif (args['type'] == 'Policy Question'):
            args['type'] = 'Policy'
            summary = re.sub( r'Policy:\s+', '', args['summary'] )
            if (summary == args['summary'] ):
                raise Exception("%s: is Policy but without summary prefix '%s'" % (key,args['summary']))
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
            raise Exception("%s: I unexpected type %s" % (key,args['type']))
    
    return(features, policies, user_stories, epics)


def add_epic_names(issues, epics):
    """Add a field epic_name to each issue."""
    for issue in issues:
        if ('epic' in issue):
            epic_key = issue['epic']
            for epic in epics:
                if (epic['key'] == epic_key):
                    issue['epic_name'] = epic['summary']
                    issue['epic_ref'] = '\\hyperlink{%s}{%s}' % (issue['epic_name'],issue['epic_name'])
                    break
            if ('epic_name' not in issue):
                raise Exception("%s: Failed to find epic name for %s" % (issue['key'],epic_key))


def add_story_epics(issues, user_stories_by_key):
    """Add a field story_epics to each issue in issues base on the epics its stories rely on"""
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
                    print("Non-story %s linked from %s, link ignored" % (target,issue['key']))
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
                for target in sorted(issue['issuelinks'][linktype], key = key_number):
                    targets.append("\\hyperlink{%s}{%s}" % (target, target))
                issue['related'] += '\n'+linktype+': '+', '.join(targets)+'\n'


def get_issue(issues, target, msg="issues"):
    """Lookup issue based on the key.

    FIXME - This is mindblowingly inefficient! need lookup by key
    """
    for t in (issues):
        if (t['key'] == target):
            return(t)
    raise Exception("Cannot find %s in %s" % (target,msg))
    

def infer_feature_policy_priorities(user_stories, other, fp, modify=True):
    """Infer feature and policy priorities from user_story priorities

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
                if (priority is None or PRIORITY_TO_VALUE[p]>PRIORITY_TO_VALUE[priority]):
                    priority = p
        else:
            print("Issue %s is not relied upon by any issue" % (issue['key']))
        if (priority is None):
            print("No priority calculated for %s, treating as Low" % (issue['key']))
            priority = 'Low'
        elif (PRIORITY_TO_VALUE[issue['priority']]<PRIORITY_TO_VALUE[priority]):
            print("%s has priority %s, which is LOWER from inferred priority %s" % (issue['key'], issue['priority'], priority))
            if (modify):
                print("%s priority changed %s -> %s" % (issue['key'], issue['priority'], priority))
                issue['priority'] = priority
        elif (PRIORITY_TO_VALUE[issue['priority']]>PRIORITY_TO_VALUE[priority]):
            print("%s has priority %s, which is higher than inferred priority %s" % (issue['key'], issue['priority'], priority))
            

def check_story_priorities(features, policies, user_stories, modify=False):
    """Infer story priorities from feature and policy priorities as a sanity check.

    The story priority calculated will be the lowest of the priorities of the 
    features and policies it relies upon. A warning will be shown if the actual
    story priority is lower than this.

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
                    raise Exception("Cannot find %s in features or priorities" % (target))
                if (priority is None or PRIORITY_TO_VALUE[p]<PRIORITY_TO_VALUE[priority]):
                    priority = p
        else:
            print("Issue %s does not rely on any feature or policy" % (issue['key']))
        if (priority is None):
            print("No priority calculated for %s, treating as Low" % (issue['key']))
            priority = 'Low'
        elif (PRIORITY_TO_VALUE[issue['priority']]<PRIORITY_TO_VALUE[priority]):
            print("%s has priority %s, lower than inferred priority %s" % (issue['key'], issue['priority'], priority))
            if (modify):
                print("Setting %s to priority %s" % (issue['key'],priority))
                issue['priority'] = priority


### Options
#
parser = OptionParser(description="Make query to Jira and format results as text message to stdout")
group = OptionGroup(parser, "Debug Options")
group.add_option("-u", "--show-uri", dest="show_uri", action="store_true",
                 help="show query URI and exit")
group.add_option("-s", "--show-xml", dest="show_xml", action="store_true",
                 help="show XML response from Jira and exit")
parser.add_option_group(group)
(options, args) = parser.parse_args()

### Config
#
# Look in current dirs, user home, script install
config = ConfigParser.RawConfigParser()
for loc in os.curdir, os.path.expanduser("~"), os.path.dirname(__file__):
    try: 
        with open(os.path.join(loc,'irs_reporter.cfg')) as source:
            config.readfp( source )
        break #one success is enough
    except IOError:
        pass
#
section = 'irs_reporter'
name = config.get(section,'name')
username = config.get(section,'username')
password = config.get(section,'password')
baseuri = config.get(section,'baseuri')
query = config.get(section,'query') #as cut-paste from advanced search box in Jira
# See
# https://confluence.atlassian.com/jira/displaying-search-results-in-xml-185729644.html
# for a description of fields available
fields = [ 'key', 'type', 'summary', 'description', 'status', 'link', 'component', 'priority', 'issuelinks', 'allcustom' ]

if (not query):
    raise Exception("No query in config!")

# Get data from Jira
tree = query_jira(query, username, password, fields, options)
(features, policies, user_stories, epics) = split_jira_results(tree, fields)
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

script_dir = os.path.dirname(__file__)
template_dir = os.path.join(script_dir,'templates')
template_prefix = 'irs_'

# Use standard templates ala 
# http://docs.python.org/2/library/string.html#format-examples
wrapper_template = open(os.path.join(template_dir,template_prefix+"wrapper.tpl")).read()

# Now wrap issues
wrapper_args = { 'name': name,
                 'now': str(datetime.now()),
                 'date': str(date.today()),
                 'query': query,
                 'program': os.path.basename(__file__) }


feature_template = """{keytarget}
\subsubsection{{Feature: {summary} ({key}, {priority})}}

{description}
{related}

"""
features_txt = ''
for priority in PRIORITIES:
    features_txt += "\subsection{{%s priority features}}\n\n" % (priority) 
    for issue in sorted(features, key = issue_number):
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
    for issue in sorted(policies, key = issue_number):
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
    user_stories_txt += "\\hypertarget{%s}{}\n\subsection{%s}\n\n" % (epic_name,epic_name)
    for issue in sorted(user_stories, key = lambda i: ((4 - PRIORITY_TO_VALUE[i['priority']]) * 10000 + issue_number(i))):
        if (issue['epic_name'] == epic_name):
            if (issue['related'] == ''):
                issue['related'] = "\\textit{No features or policies have been associated with this user story.}\n";
            user_stories_txt += user_stories_template.format(**issue)


txt = wrapper_template.format(features=features_txt,
                              policies=policies_txt,
                              user_stories=user_stories_txt,
                              **wrapper_args)

filename = template_prefix+'report.tex'
fh = open(filename,'w')
fh.write(txt)
fh.close()
print("Written %s, done." % (filename))
