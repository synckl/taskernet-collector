import re
from urllib.parse import urlparse, parse_qs, quote_plus
import xml.etree.ElementTree as ET
import json
import functools
import os
import unicodedata
import itertools

import googleplay_api as gplay

PRAW_SITE_NAME = 'taskernet_bot'
MONITORED_SUBREDDITS = 'tasker+taskernet'

TASKERNET_RE = re.compile(r'https://taskernet\.com/shares[^\\]*?id=[\w\d+%.-]+')
COLLECTOR_COMMAND_SEARCH_RE = re.compile(r'search "(?P<terms>.*?)"', re.IGNORECASE)
HTML_TAG_RE = re.compile(r'<.*?>')
UNICODE_RE = re.compile(r'[^\x00-\x7F]+')
COLLECTOR_IGNORE_RE = re.compile(r'\[no\-collect\]')
XML_NS_RE = re.compile(r'</?.+?:.+?>')

def remove_html_tags(text):
  return re.sub(HTML_TAG_RE, '', text)

def remove_unicode(text):
  return re.sub(UNICODE_RE, ' ', text)

# Either share_link or both user and share_id are required
def share_object_id(share_link=None, user=None, share_id=None):
  try:
    if share_link is not None:
      user, share_id = parse_link(share_link)
    return f'{user}_{share_id}'
  except:
    return None

def parse_link(share_link):
  try:
    parsed = urlparse(share_link)
    qparams = parse_qs(parsed.query)

    user = quote_plus(qparams['user'][0])
    share_id = quote_plus(qparams['id'][0])
    return user, share_id
  except:
    return None, None

def parse_datadef():
  lookup = {
    'state': {},
    'action': {},
    'event': {}
  }

  tree = ET.parse('datadef.xml')
  root = tree.getroot()

  for element in root:
    if element.tag in {'state', 'action', 'event'}:
      lookup[element.tag][element.attrib['code']] = { 'name': element.attrib['nameLocal'] }

  with open('datadef.json', 'w') as f:
    json.dump(lookup, f)

@functools.lru_cache(maxsize=16)
def get_datadef():
  datadef_dir = os.path.dirname(os.path.realpath(__file__))
  datadef_file = os.path.join(datadef_dir, 'datadef.json')
  with open(datadef_file, 'r') as f:
    return json.load(f)

def remove_control_characters(s):
  return ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C')

def remove_namespaces(xml):
  ns_tags = list(set(XML_NS_RE.findall(xml)))
  repls = [e.replace(':', '_') for e in ns_tags]
  for tag, repl in itertools.zip_longest(ns_tags, repls):
    xml = xml.replace(tag, repl)
  return xml

def parse_tasker_data(tasker_data):
  lookup = get_datadef()
  try:
    root = ET.fromstring(tasker_data)
  except:
    tasker_data = remove_namespaces(remove_control_characters(tasker_data))
    root = ET.fromstring(tasker_data)

  all_tags = set()
  all_names = set()
  plugins = set()
  for element in root.iter():
    if element.tag in {'State', 'Event', 'Action'} and element.find('code') is not None:
      code = element.find('code').text
      tasker_element = lookup[element.tag.lower()][code] if code in lookup[element.tag.lower()] else None
      if tasker_element:
        if 'excludeItemName' not in tasker_element:
          all_names.add(tasker_element['name'])
        if 'tags' in tasker_element:
          all_tags.update(tasker_element['tags'])
      else:
        if element.find('./Bundle/Vals/plugintypeid') is not None or element.find('./Bundle/Vals/net.dinglisch.android.tasker.subbundled') is not None:
          plugins.add(element.find('Str[@sr="arg1"]').text)
    elif element.tag == 'App' and element.find('appPkg') is not None and element.find('appPkg').text is not None:
      pkgs = element.find('appPkg').text.split(',')
      plugins.update(p.strip() for p in pkgs if '%' not in p)
  
  return list(all_tags), list(all_names), list(plugins)
