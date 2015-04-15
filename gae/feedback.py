# coding: UTF-8

import os
import sys
from google.appengine.ext.webapp import template

import datetime
import email.utils
import hashlib
import time
import urlparse
import urllib
import urllib2

import logging

from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import json
import pprint

import myconfig

class Topic(db.Model):
  # key_name = topic_name
  # parent = None
  queries = db.StringListProperty()

class SearchCache(db.Model):
  # key_name = query
  # parent = None
  max_id = db.StringProperty()
  min_id = db.StringProperty()
  ids = db.StringListProperty()

class Tweet(db.Model):
  # key_name = tweet_id
  # parent = None
  data = db.TextProperty()

class Profile(db.Model):
  # key_name = user_id
  # parent = None
  since_id = db.StringProperty()

class History(db.Model):
  # key_name = topic_name
  # parent = Profile
  max_id = db.StringProperty()
  min_id = db.StringProperty()

class Label(db.Model):
  # key_name = tweet_id
  # parent = Profile
  name = db.StringProperty()

def GetLabels(user):
  profile = Profile.get_or_insert(key_name=user.user_id())
  return Label.all().ancestor(profile)


def SetLabel(profile, request):
  tweet_id = request.get('id')
  label = Label.get_or_insert(key_name=tweet_id, parent=profile)
  label.name = request.get('name')
  label.put()
  return label


class TwitterApi(object):
  def __init__(self, access_token):
    self._access_token = access_token

  def Search(self, query):
    SEARCH_URL = 'https://api.twitter.com/1.1/search/tweets.json'
    request = urllib2.Request(SEARCH_URL + '?' + query)
    request.add_header('Authorization', 'Bearer ' + self._access_token)
 
    response = urllib2.urlopen(request)
    return response.read()


def TwitterSearch(query):
  return TwitterApi(myconfig.BEARER_ACCESS_TOKEN).Search(query)


def ShouldFiltered(status):
  if status.get('retweet_count', 0) != 0:
    return True

  if IsUser(status, myconfig.FILTERED_USERS):
    return True

  return False


def IsUser(status, users):
  if status.get('user', {}).get('screen_name') in users:
    return True

  for mentions in status.get('entities', {}).get('user_mentions', []):
    if mentions.get('screen_name') in users:
      return True

  return False


class Tweets(object):
  def __init__(self, response):
    self._response = response
    self._statuses = []
    self._max_id = 0
    self._min_id = sys.maxint

    for status in response['statuses']:
      if ShouldFiltered(status):
        continue
      self._statuses.append(status)
      self._max_id = max(self._max_id, status['id'])
      self._min_id = min(self._min_id, status['id'])

  def GetSize(self):
    return len(self.GetTweets())

  def GetTweets(self):
    return self._statuses

  def GetMaxId(self):
    return str(self._max_id)

  def GetMinId(self):
    return str(self._min_id)

  def SetData(self, id, dict):
    for status in self._statuses:
      if status['id_str'] == id:
        for key in dict:
          status[key] = dict[key]
        return True
    return False


def SearchAllSinceId(q, since_id):
  escaped_q = urllib.quote(q.encode('utf-8'))
  base_query = "q=%s&count=100&since_id=%d" % (escaped_q, since_id)
  response_dict = PerformSearch(base_query)
  tweets = Tweets(response_dict)

  while tweets.GetSize() == 100:
    max_id = int(tweets.GetMinId()) - 1
    query = base_query + "&max_id=%d" % max_id
    response_dict = PerformSearch(query)
    tweets = Tweets(response_dict)


def StoreSearchCache(query, response):
  ids = StoreTweets(response)
  if not ids:
    return

  cache = SearchCache.get_or_insert(key_name=unicode(query, 'utf-8'), ids=[])
  ids = sorted(set(ids + cache.ids), reverse=True)

  # 5,000 is the limit.
  ids = ids[0:5000]
  cache.ids = ids
  cache.max_id = ids[0]
  cache.min_id = ids[-1]
  cache.put()


def StoreTweets(response):
  ids = []
  tweets = Tweets(response)

  for tweet in tweets.GetTweets():
    id = tweet['id_str']
    Tweet.get_or_insert(key_name = id, data = json.dumps(tweet))
    ids.append(id)
  return ids


def UpdateProfile(since_id):
  user = users.get_current_user()
  if not user:
    return False

  profile = Profile.get_or_insert(key_name=user.user_id())
  profile.since_id = since_id
  profile.put()
  return True


def AppendLabel(response):
  user = users.get_current_user()
  if not user:
    return False

  tweets = Tweets(response)
  if tweets.GetSize() == 0:
    return False

  labels = GetLabels(user).order('__key__')
  min_key = db.Key.from_path('Profile', user.user_id(),
                             'Label', tweets.GetMinId())
  max_key = db.Key.from_path('Profile', user.user_id(),
                             'Label', tweets.GetMaxId())
  labels = labels.filter('__key__ >=', min_key).filter('__key__ <=', max_key)

  modified = False
  for label in labels:
    if label.name == 'star':
      modified |= tweets.SetData(label.key().name(), {'x_label': 'star'})

  return modified


class Account(webapp.RequestHandler):
  def get(self):
    response = {}
    user = users.get_current_user()
    if user:
      response['email'] = user.email()
      response['login'] = True
      response['logout_url'] = users.create_logout_url('/feedback/')
    else:
      response['login'] = False
      response['login_url'] = users.create_login_url('/feedback/')

    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write(json.dumps(response))


class Command(webapp.RequestHandler):
  def get(self):
    response = {}
    user = users.get_current_user()
    if user:
      profile = Profile.get_or_insert(key_name=user.user_id())
      new_label = SetLabel(profile, self.request)
      response['response'] = 'ok'
    else:
      response['response'] = 'login'
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write(json.dumps(response))


class ShowCron(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'

    q = unicode(myconfig.SHOW_CRON_QUERY, 'utf-8')
    cache = SearchCache.get_by_key_name(q)

    if not cache:
      self.response.out.write('no data')
      return

    # ids are reverse ordered.
    statuses = []
    for id in cache.ids:
      tweet = Tweet.get_by_key_name(id)
      if not tweet:
        # Something bad was happen.
        continue

      statuses.append(json.loads(tweet.data))

    response_dict = {'statuses': statuses}

    pp = pprint.PrettyPrinter(indent=2)
    response_pp = pp.pformat(response_dict)
    self.response.out.write(response_pp)


def SearchNewTweets(query_unicode):
  cache = SearchCache.get_by_key_name(query_unicode)
  since_id = 0
  if cache:
    since_id = int(cache.max_id) + 1

  SearchAllSinceId(query_unicode, since_id)

class Cron(webapp.RequestHandler):
  def get(self):
    for query in myconfig.QUERIES:
      SearchNewTweets(unicode(query, 'utf-8'))

    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write('OK')


class Download(webapp.RequestHandler):
  def get(self):
    response = {'statuses': []}
    user = users.get_current_user()
    if user:
      # TODO: merge the below function
      twitter_queries = urlparse.parse_qs(self.request.query_string)
      since_id_str = '0';
      if 'since_id' in twitter_queries:
        since_id_str = twitter_queries['since_id'][0]
      min_key = db.Key.from_path('Profile', user.user_id(),
                                 'Label', since_id_str)

      # Get label
      labels = (GetLabels(user).filter('name =', 'star').
                filter('__key__ >=', min_key).order('__key__'))
      for label in labels:
        tweet = Tweet.get_by_key_name(label.key().name())
        if not tweet:
          # Invalid state
          continue
        response['statuses'].append(json.loads(tweet.data))
      response['response'] = 'ok'
      AppendLabel(response)
    else:
      response['response'] = 'login'
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write(json.dumps(response))

class DownloadTsv(webapp.RequestHandler):
  def get(self):
    tsv = []
    user = users.get_current_user()
    if user:
      # TODO: merge the above function
      twitter_queries = urlparse.parse_qs(self.request.query_string)
      since_id_str = '0';
      if 'since_id' in twitter_queries:
        since_id_str = twitter_queries['since_id'][0]
      min_key = db.Key.from_path('Profile', user.user_id(),
                                 'Label', since_id_str)

      # Get label
      labels = (GetLabels(user).filter('name =', 'star').
                filter('__key__ >=', min_key).order('__key__'))
      for label in labels:
        tweet = Tweet.get_by_key_name(label.key().name())
        if not tweet:
          # Invalid state
          continue
        tweet_json = json.loads(tweet.data)
        text = tweet_json['text'].replace('\n', ' ')
        user = tweet_json['user']['screen_name']
        id = tweet_json['id_str']
        url = "http://twitter.com/%s/status/%s" % (user, id)
        date = time.strftime("%Y-%m-%d %H:%M:%S",
                             email.utils.parsedate(tweet_json['created_at']))
        tsv.append('\t'.join([text, url, date]))

    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write('\n'.join(tsv))


def PerformSearch(query_string):
  response_dict = json.loads(TwitterSearch(query_string))

  twitter_queries = urlparse.parse_qs(query_string)
  StoreSearchCache(twitter_queries['q'][0], response_dict)
  return response_dict


def SearchWithCache(request):
  query_string = request.query_string
  twitter_queries = urlparse.parse_qs(query_string)

  if 'max_id' not in twitter_queries:
    return PerformSearch(query_string)

  max_id = twitter_queries['max_id'][0]
  query = twitter_queries['q'][0]
  count = int(twitter_queries.get('count', ['15'])[0])

  cache = SearchCache.get_by_key_name(unicode(query, 'utf-8'))
  if not cache:
    return PerformSearch(query_string)

  if not (cache.min_id < max_id < cache.max_id):
    return PerformSearch(query_string)

  cached_ids = []
  # ids are reverse ordered.
  for id in cache.ids:
    if id > max_id:
      continue

    cached_ids.append(id)
    if len(cached_ids) >= count:
      break
  else:
    # If len(cached_ids) is less than count, do not use the cache.
    # TODO: Nice to use the cache.
    return PerformSearch(query_string)

  statuses = []
  # ids are reverse ordered.
  for id in cached_ids:
    tweet = Tweet.get_by_key_name(id)
    if not tweet:
      # Something bad was happen.
      return PerformSearch(query_string)

    statuses.append(json.loads(tweet.data))

  # Set search_metadata
  next_results = '&'.join(['?max_id=%d' % (int(cached_ids[-1]) - 1),
                           'q=%s' % urllib.quote(query),
                           'include_entities=1']) 
  refresh_url = '&'.join(['?since_id=%s' % cached_ids[0],
                          'q=%s' % urllib.quote(query),
                          'include_entities=1']) 
  search_metadata = {'count': count,
                     'max_id': int(cached_ids[0]),
                     'max_id_str': cached_ids[0],
                     'next_results': next_results,
                     'query': unicode(query, 'utf-8'),
                     'refresh_url': refresh_url,
                     'since_id': 0,
                     'since_id_str': '0',}

  response_dict = {'search_metadata': search_metadata,
                   'statuses': statuses}
  AppendLabel(response_dict)
  return response_dict


def GetCachedTweets(request):
  query_string = request.query_string
  twitter_queries = urlparse.parse_qs(query_string)

  since_id = "0"
  if 'since_id' in twitter_queries:
    since_id = twitter_queries['since_id'][0]
  query = twitter_queries['q'][0]
  count = int(twitter_queries.get('count', ['15'])[0])

  cache = SearchCache.get_by_key_name(unicode(query, 'utf-8'))
  if not cache:
    return {}

  if since_id > cache.max_id:
    return {}

  cached_ids = []
  # ids are reverse ordered.
  for id in reversed(cache.ids):
    if id < since_id:
      continue

    cached_ids.append(id)
    if len(cached_ids) >= count:
      break

  statuses = []
  for id in cached_ids:
    tweet = Tweet.get_by_key_name(id)
    if not tweet:
      # Something bad was happen.
      continue

    statuses.append(json.loads(tweet.data))

  # Set search_metadata
  next_results = '&'.join(['?since_id=%d' % (int(cached_ids[-1]) + 1),
                           'q=%s' % urllib.quote(query),
                           'include_entities=1']) 
  refresh_url = '&'.join(['?since_id=%s' % cached_ids[0],
                          'q=%s' % urllib.quote(query),
                          'include_entities=1']) 
  search_metadata = {'count': count,
                     'max_id': int(cached_ids[-1]),
                     'max_id_str': cached_ids[-1],
                     'next_results': next_results,
                     'query': unicode(query, 'utf-8'),
                     'refresh_url': refresh_url,
                     'since_id': int(cached_ids[0]),
                     'since_id_str': cached_ids[0],}

  response_dict = {'search_metadata': search_metadata,
                   'statuses': statuses}
  AppendLabel(response_dict)
  return response_dict


def GetUnreadTweets(request):
  query_string = request.query_string
  twitter_queries = urlparse.parse_qs(query_string)

  since_id_str = "0"
  if 'since_id' in twitter_queries:
    since_id_str = twitter_queries['since_id'][0]
  else:
    user = users.get_current_user()
    if user:
      profile = Profile.get_or_insert(key_name=user.user_id())
      since_id_str = (profile.since_id or "0")

  count = int(twitter_queries.get('count', ['50'])[0])

  min_key = db.Key.from_path('Tweet', since_id_str)
  tweets = (Tweet.all().filter('__key__ >=', min_key).order('__key__').
           fetch(count))

  statuses = []
  cached_ids = []  # cached_id contatins filtered ids too.
  for tweet in tweets:
    cached_ids.append(tweet.key().name())
    status = json.loads(tweet.data)
    if ShouldFiltered(status):
      continue
    statuses.append(status)

  if cached_ids:
    max_id = int(cached_ids[-1])
    since_id = int(cached_ids[0])
    next_since_id = max_id + 1
  else:
    # No result was found.
    max_id = int(since_id_str)
    since_id = max_id
    next_since_id = max_id

  # No more unread tweets.
  if len(cached_ids) != count:
    status = {
      'created_at': datetime.datetime.utcnow().strftime('%a %b %d %X +0000 %Y'),
      'id': max_id,
      'id_str': str(max_id),
      'text': 'no more tweets',
      'user': { 'name': 'Feedback',
                'screen_name': 'Feedback',
                'profile_image_url': '/feedback/icon_32.png', },
      }
    statuses.append(status)


  # Set search_metadata
  next_results = '&'.join(['?since_id=%d' % next_since_id,
                           'include_entities=1']) 
  refresh_url = '&'.join(['?since_id=%d' % since_id,
                          'include_entities=1']) 
  search_metadata = {'count': count,
                     'max_id': max_id,
                     'max_id_str': str(max_id),
                     'next_results': next_results,
                     'refresh_url': refresh_url,
                     'since_id': since_id,
                     'since_id_str': str(since_id),}

  response_dict = {'search_metadata': search_metadata,
                   'statuses': statuses}
  AppendLabel(response_dict)

  # Update user's since_id.  Note, recorded since_id does not contains the
  # latest session.  It enables to show the same tweets in different browsers.
  #
  # UpdateProfile(str(since_id))

  return response_dict


# Search with SearchCache
class Search(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    response_dict = SearchWithCache(self.request)
    self.response.out.write(json.dumps(response_dict))

# Get next tweets
class Next(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    response_dict = GetUnreadTweets(self.request)
    self.response.out.write(json.dumps(response_dict))


# Update the since_id of the profile.
class Update(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    response = {'statuses': []}
    user = users.get_current_user()
    if not user:
      response['response'] = 'login'
      self.response.out.write(json.dumps(response))
      return

    query_string = self.request.query_string
    twitter_queries = urlparse.parse_qs(query_string)
    if 'since_id' in twitter_queries:
      max_id_str = twitter_queries['since_id'][0]
      UpdateProfile(max_id_str)
    response['response'] = 'ok'

    self.response.out.write(json.dumps(response))


class SearchTest(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write('Search Test\n')

    response_dict = json.loads(TwitterSearch(self.request.query_string))
    message = ''
    for result in response_dict['statuses']:
      message += result['created_at'].encode('utf-8')[4:16] + '\t'
      message += result['id_str'].encode('utf-8') + '\t'
      message += result['text'].encode('utf-8') + '\n'
    self.response.out.write(message)

    AppendLabel(response_dict)

    pp = pprint.PrettyPrinter(indent=2)
    response_pp = pp.pformat(response_dict)
    self.response.out.write(response_pp)


class Test(webapp.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
    self.response.out.write('Test')
    output = ''
    output += 'remote_addr: %s\n' % self.request.remote_addr
    output += 'url: %s\n' % self.request.url
    output += 'path: %s\n' % self.request.path
    output += 'query_string: %s\n' % self.request.query_string
    output += 'headers: %s\n' % self.request.headers
    output += 'cookies: %s\n' % self.request.cookies
    self.response.out.write(output)


application = webapp.WSGIApplication(
                                     [('/feedback/account', Account),
                                      ('/feedback/command', Command),
                                      ('/feedback/cron', Cron),
                                      ('/feedback/download', Download),
                                      ('/feedback/download_tsv', DownloadTsv),
                                      ('/feedback/next', Next),
                                      ('/feedback/search', Search),
                                      ('/feedback/search_test', SearchTest),
                                      ('/feedback/showcron', ShowCron),
                                      ('/feedback/test', Test),
                                      ('/feedback/update', Update)],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
