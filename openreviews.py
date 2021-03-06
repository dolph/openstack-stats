#!/usr/bin/env python
#
# Copyright (C) 2011 - Soren Hansen
# Copyright (C) 2013 - Red Hat, Inc.
#

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import calendar
import datetime
import optparse
import os
import os.path
import sys

import utils


optparser = optparse.OptionParser()
optparser.add_option('-p', '--project', default='projects/nova.json',
        help='JSON file describing the project to generate stats for')
optparser.add_option('-a', '--all', action='store_true',
        help='Generate stats across all known projects (*.json)')
optparser.add_option('-u', '--user', default='russellb', help='gerrit user')
optparser.add_option('-k', '--key', default=None, help='ssh key for gerrit')
optparser.add_option('-s', '--stable', action='store_true',
        help='Include stable branch commits')
optparser.add_option('-l', '--longest-waiting', type='int', default=5,
        help='Show n changesets that have waited the longest)')
optparser.add_option('-m', '--waiting-more', type='int', default=7,
        help='Show number of changesets that have waited more than n days)')

options, args = optparser.parse_args()

projects = utils.get_projects_info(options.project, options.all)

if not projects:
    print "Please specify a project."
    sys.exit(1)

changes = utils.get_changes(projects, options.user, options.key,
        only_open=True)

waiting_on_submitter = []
waiting_on_reviewer = []

now = datetime.datetime.utcnow()
now_ts = calendar.timegm(now.timetuple())

def sec_to_period_string(seconds):
    days = seconds / (3600 * 24)
    hours = (seconds / 3600) - (days * 24)
    minutes = (seconds / 60) - (days * 24 * 60) - (hours * 60)
    return '%d days, %d hours, %d minutes' % (days, hours, minutes)



for change in changes:
    if 'rowCount' in change:
        continue
    if not options.stable and 'stable' in change['branch']:
        continue
    if change['status'] != 'NEW':
        # Filter out WORKINPROGRESS
        continue
    latest_patch = change['patchSets'][-1]
    waiting_for_review = True
    approvals = latest_patch.get('approvals', [])
    approvals.sort(key=lambda a:a['grantedOn'])
    for review in approvals:
        if review['type'] not in ('CRVW', 'VRIF'):
            continue
        if review['value'] in ('-1', '-2'):
            waiting_for_review = False
            break
    # The createdOn timestamp on the patch isn't what we want.
    # It's when the patch was written, not submitted for review.
    # The next best thing in the data we have is the time of the
    # first review.  When all is working well, jenkins or smokestack
    # will comment within the first hour or two, so that's better
    # than the other timestamp, which may reflect that the code
    # was written many weeks ago, even though it was just recently
    # submitted for review.
    if approvals:
        change['age'] = now_ts - approvals[0]['grantedOn']
    else:
        change['age'] = now_ts - latest_patch['createdOn']
    if waiting_for_review:
        waiting_on_reviewer.append(change)
    else:
        waiting_on_submitter.append(change)


def average_age(changes):
    total_seconds = 0
    for change in changes:
        total_seconds += change['age']
    avg_age = total_seconds / len(changes)
    return sec_to_period_string(avg_age)

def median_age(changes):
    changes = sorted(changes, key=lambda change: change['age'])
    median_age = changes[len(changes)/2]['age']
    return sec_to_period_string(median_age)

def number_waiting_more_than(changes, seconds):
    index = 0
    for change in changes:
        if change['age'] > seconds:
            return len(changes) - index
        index += 1
    return 0

age_sorted_waiting_on_reviewer = sorted(waiting_on_reviewer,
                                        key=lambda change: change['age'])


print 'Projects: %s' % [project['name'] for project in projects]
print 'Total Open Reviews: %d' % (len(waiting_on_reviewer) +
        len(waiting_on_submitter))
print 'Waiting on Submitter: %d' % len(waiting_on_submitter)
print 'Waiting on Reviewer: %d' % len(waiting_on_reviewer)
print ' --> Average wait time: %s' % average_age(waiting_on_reviewer)
print ' --> Median wait time: %s' % median_age(waiting_on_reviewer)
print ' --> Number waiting more than %i days: %i' % (
    options.waiting_more, number_waiting_more_than(
        age_sorted_waiting_on_reviewer,
        60*60*24*options.waiting_more))
print ' --> Longest waiting reviews:'
for change in age_sorted_waiting_on_reviewer[-options.longest_waiting:]:
    print '    --> %s %s \n          (%s)' % (
        sec_to_period_string(change['age']),
        change['url'], change['subject'])
