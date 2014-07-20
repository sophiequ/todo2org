#!/usr/bin/env python
from datetime import datetime, date
from dateutil.relativedelta import relativedelta as rd, MO, TU, WE, TH, FR, SA, SU
from email.Iterators import typed_subpart_iterator
from email.header import decode_header
import logging
import re
import os
import email
import itertools
import time
import sys
import argparse

logging.basicConfig(format='%(asctime)s %(levelname)s - %(message)s', filename='todo2org.log', level=logging.DEBUG)

"""
ToDo:
 - [X] argparse
 - [X] Output encoding flag
 - [X] config variables
 - [X] entry template?
 - [ ] emacsclient and org-protocol method (urlencode needed?)
 - [ ] test suite with messages
 - [ ] logger
"""

CONFIG = {
    # customize your configuration here by overwriting entries from DEFAULT_ENCODING, e.g.
    # 'content_layout':   u"{body}"
}


##################################################################################################################

DEFAULT_CONFIG = {
    'time_separator': '#',
    'org_entry_layout': u"* {subject}{timestamp}\n\n{content}\n",
    'timestamp_layout': u"\nSCHEDULED: {timestamp}",
    'content_layout':   u"From: {from}\nTo: {to}\nDate: {date}\nSubject: {subject}\n\n{body}"
}


def get_date_by_relative_str(curdate, relativestr):
    """
    get new date by adding relative date/time given in relativestr to curdate

    >>> print get_date_by_relative_str(date(2014,01,15), "1w")
    2014-01-22
    >>> print get_date_by_relative_str(date(2014,01,31), "4w")
    2014-02-28
    >>> print get_date_by_relative_str(date(2014,07,17), "mon")
    2014-07-21
    >>> print get_date_by_relative_str(date(2014,07,17), "mo")
    2014-07-21
    >>> print get_date_by_relative_str(date(2014,07,21), "mo")
    2014-07-28
    >>> print get_date_by_relative_str(date(2014,07,17), "mond")
    2014-07-21
    >>> print get_date_by_relative_str(date(2014,07,17), "monday")
    2014-07-21
    >>> print get_date_by_relative_str(date(2014,07,17), "10d")
    2014-07-27
    >>> print get_date_by_relative_str(date(2014,07,31), "2m")
    2014-09-30
    >>> print get_date_by_relative_str(date(2012,02,29), "3y")
    2015-02-28
    >>> print get_date_by_relative_str(date(2014,02,01), "04-25")
    2014-04-25
    >>> print get_date_by_relative_str(date(2014,02,01), "25")
    2014-02-25
    >>> print get_date_by_relative_str(date(2014,02,01), "01")
    2014-03-01
    >>> print get_date_by_relative_str(date(2014,02,01), "1")
    2014-03-01
    >>> print get_date_by_relative_str(date(2014,02,05), "1")
    2014-03-01
    >>> print get_date_by_relative_str(date(2014,02,01), "jan14")
    2015-01-14
    >>> print get_date_by_relative_str(date(2014,02,01), "december-25")
    2014-12-25
    >>> print get_date_by_relative_str(date(2014,02,01), "2014-1-1")
    2014-01-01
    >>> print get_date_by_relative_str(date(2014,02,01), "2015-12-31")
    2015-12-31
    >>> print get_date_by_relative_str(date(2014,02,01), "tom")
    2014-02-02
    >>> print get_date_by_relative_str(date(2014,02,01), "tomorrow")
    2014-02-02
    >>> print get_date_by_relative_str(datetime(2014,02,01,12,30,59), "tomorrow")
    2014-02-02 12:30:59
    >>> print get_date_by_relative_str(datetime(2014,02,01,12,30,59), "tom#1000")
    2014-02-02 10:00:00
    >>> print get_date_by_relative_str(datetime(2014,07,17,12,30,59), "mo#10")
    2014-07-21 10:00:00
    >>> print get_date_by_relative_str(datetime(2014,07,17,12,30,59), "4-3#1035")
    2014-04-03 10:35:00
    >>> print get_date_by_relative_str(datetime(2014,02,01,12,30,59), "t#2014")
    2014-02-01 20:14:00
    >>> print get_date_by_relative_str(date(2014,02,05), "today")
    2014-02-05
    """

    DATE_MATCHERS = dict({
        r"to?d?a?y?$"                         : lambda d, m: d,
        r"tomo?r?r?o?w?"                      : lambda d, m: d + rd(days=1),
        r"mon?d?a?y?"                         : lambda d, m: (d + rd(weekday=MO)) if (d + rd(weekday=MO) > d) else (d + rd(weekday=MO(2))),   # use next weekday if the result is not in the future
        r"tue?s?d?a?y?"                       : lambda d, m: (d + rd(weekday=TU)) if (d + rd(weekday=TU) > d) else (d + rd(weekday=TU(2))),
        r"wed?n?e?s?d?a?y?"                   : lambda d, m: (d + rd(weekday=WE)) if (d + rd(weekday=WE) > d) else (d + rd(weekday=WE(2))),
        r"thu?r?s?d?a?y?"                     : lambda d, m: (d + rd(weekday=TH)) if (d + rd(weekday=TH) > d) else (d + rd(weekday=TH(2))),
        r"fri?d?a?y?"                         : lambda d, m: (d + rd(weekday=FR)) if (d + rd(weekday=FR) > d) else (d + rd(weekday=FR(2))),
        r"sat?u?r?d?a?y?"                     : lambda d, m: (d + rd(weekday=SA)) if (d + rd(weekday=SA) > d) else (d + rd(weekday=SA(2))),
        r"sun?d?a?y?"                         : lambda d, m: (d + rd(weekday=SU)) if (d + rd(weekday=SU) > d) else (d + rd(weekday=SA(2))),
        r"^([0-9]+)d"                         : lambda d, m: d + rd(days=int(m[0])), 
        r"^([0-9]+)w"                         : lambda d, m: d + rd(weeks=int(m[0])), 
        r"^([0-9]+)m"                         : lambda d, m: d + rd(months=int(m[0])), 
        r"^([0-9]+)y"                         : lambda d, m: d + rd(years=int(m[0])), 
        r"^([0-9]{1,2})$"                     : lambda d, m: (d + rd(day=int(m[0]))) if (d + rd(day=int(m[0])) > d) else (d + rd(months=1, day=int(m[0]))),
        r"^([0-9]{1,2})-([0-9]{1,2})$"        : lambda d, m: d + rd(month=int(m[0]),day=int(m[1])),
        r"janu?a?r?y?-?([0-9]{,2})"           : lambda d, m: (d + rd(month=1,  day=int(m[0]))) if (d + rd(month=1,  day=int(m[0])) > d) else (d + rd(years=1, month=1,  day=int(m[0]))),
        r"febr?u?a?r?y?-?([0-9]{,2})"         : lambda d, m: (d + rd(month=2,  day=int(m[0]))) if (d + rd(month=2,  day=int(m[0])) > d) else (d + rd(years=1, month=2,  day=int(m[0]))),
        r"marc?h?-?([0-9]{,2})"               : lambda d, m: (d + rd(month=3,  day=int(m[0]))) if (d + rd(month=3,  day=int(m[0])) > d) else (d + rd(years=1, month=3,  day=int(m[0]))),
        r"apri?l?-?([0-9]{,2})"               : lambda d, m: (d + rd(month=4,  day=int(m[0]))) if (d + rd(month=4,  day=int(m[0])) > d) else (d + rd(years=1, month=4,  day=int(m[0]))),
        r"may-?([0-9]{,2})"                   : lambda d, m: (d + rd(month=5,  day=int(m[0]))) if (d + rd(month=5,  day=int(m[0])) > d) else (d + rd(years=1, month=5,  day=int(m[0]))),
        r"june?-?([0-9]{,2})"                 : lambda d, m: (d + rd(month=6,  day=int(m[0]))) if (d + rd(month=6,  day=int(m[0])) > d) else (d + rd(years=1, month=6,  day=int(m[0]))),
        r"july?-?([0-9]{,2})"                 : lambda d, m: (d + rd(month=7,  day=int(m[0]))) if (d + rd(month=7,  day=int(m[0])) > d) else (d + rd(years=1, month=7,  day=int(m[0]))),
        r"augu?s?t?-?([0-9]{,2})"             : lambda d, m: (d + rd(month=8,  day=int(m[0]))) if (d + rd(month=8,  day=int(m[0])) > d) else (d + rd(years=1, month=8,  day=int(m[0]))),
        r"sept?e?m?b?e?r?-?([0-9]{,2})"       : lambda d, m: (d + rd(month=9,  day=int(m[0]))) if (d + rd(month=9,  day=int(m[0])) > d) else (d + rd(years=1, month=9,  day=int(m[0]))),
        r"octo?b?e?r?-?([0-9]{,2})"           : lambda d, m: (d + rd(month=10, day=int(m[0]))) if (d + rd(month=10, day=int(m[0])) > d) else (d + rd(years=1, month=10, day=int(m[0]))),
        r"nove?m?b?e?r?-?([0-9]{,2})"         : lambda d, m: (d + rd(month=11, day=int(m[0]))) if (d + rd(month=11, day=int(m[0])) > d) else (d + rd(years=1, month=11, day=int(m[0]))),
        r"dece?m?b?e?r?-?([0-9]{,2})"         : lambda d, m: (d + rd(month=12, day=int(m[0]))) if (d + rd(month=12, day=int(m[0])) > d) else (d + rd(years=1, month=12, day=int(m[0]))),
        r"([0-9]{4})-([0-9]{,2})-([0-9]{,2})" : lambda d, m: d + rd(year=int(m[0]), month=int(m[1]), day=int(m[2]))    
    })

    TIME_MATCHERS = dict({
        r"([0-9]{2})"                : lambda d, m: d + rd(hour=int(m[0]), minute=0, second=0),
        r"([0-9]{2})([0-9]{2})"      : lambda d, m: d + rd(hour=int(m[0]), minute=int(m[1]), second=0),
    })

    if '#' in relativestr:
        daterelativestr, timerelativestr = relativestr.split("#", 2)
    else:
        daterelativestr = relativestr
        timerelativestr = None

    retval = None

    for datepatternstr, dateevaluator in DATE_MATCHERS.iteritems():
        matchgr = re.match(datepatternstr, daterelativestr)
        if matchgr:
            retval = dateevaluator(curdate, matchgr.groups())
            break

    if timerelativestr:
        for timepatternstr, timeevaluator in TIME_MATCHERS.iteritems():
            matchgr = re.match(timepatternstr, timerelativestr)
            if matchgr:
                retval = timeevaluator(retval, matchgr.groups())

    return retval


def format_as_org_datetime(dateordatetime, active=True):
    """
    return a date or datetime object in org-format

    >>> print format_as_org_datetime(datetime(2014,07,17,12,30,59))
    <2014-07-17 Thu 12:30>
    >>> print format_as_org_datetime(datetime(2014,07,17,12,30,59), active=False)
    [2014-07-17 Thu 12:30]
    >>> print format_as_org_datetime(date(2014,07,17), active=False)
    [2014-07-17 Thu]
    """

    import locale
    locale.setlocale(locale.LC_TIME, "en_US")

    encl = lambda x: "<%s>" % x if active else "[%s]" % x

    try:
        dateordatetime.time()  # check if a datetime
        return encl(dateordatetime.strftime("%Y-%m-%d %a %H:%M"))
    except:
        return encl(dateordatetime.strftime("%Y-%m-%d %a"))


def get_message_header(header_text, default="ascii"):
    """Decode the specified header"""
    # from http://ginstrom.com/scribbles/2007/11/19/parsing-multilingual-email-with-python/

    headers = decode_header(header_text)
    header_sections = [unicode(text, charset or default) for text, charset in headers]
    return u"".join(header_sections)


def get_message_charset(message, default="ascii"):
    """Get the message charset"""
    # from http://ginstrom.com/scribbles/2007/11/19/parsing-multilingual-email-with-python/

    if message.get_content_charset():
        return message.get_content_charset()

    if message.get_charset():
        return message.get_charset()

    return default


def get_message_body(message):
    """Get the body of the email message"""
    # from http://ginstrom.com/scribbles/2007/11/19/parsing-multilingual-email-with-python/

    if message.is_multipart():
        text_parts = [part for part in typed_subpart_iterator(message, 'text', 'plain')]
        body = []
        for part in text_parts:
            charset = get_message_charset(part, get_message_charset(message))
            body.append(unicode(part.get_payload(decode=True), charset, "replace"))
        return u"\n".join(body).strip()

    else:
        if message.get_content_type() == "text/plain":
            body = unicode(message.get_payload(decode=True), get_message_charset(message), "replace")
            return body.strip()
        else:
            return ""


def remove_signature(bodystr):
    return u"\n".join(itertools.takewhile(lambda x: x != "-- ", bodystr.split("\n")))


def indent(bodystr, indentation):
    return bodystr.replace("\n", "\n"+indentation)


def message2org(message, outfile, config, encoding):
    try:

        message = email.message_from_string(messagestr)

        with open("debug.txt", "a") as logfile:
            logfile.write("="*80+"\n")
            logfile.write(str(datetime.now()) + "\n")
            logfile.write(str(message))

        msg_charset = get_message_charset(message)
        logging.debug("charset is " + msg_charset)

        msg_subject = get_message_header(message['Subject'] or "No Subject", default=msg_charset)
        logging.debug("subject is " + msg_subject)

        msg_from = get_message_header(message['From'], default=msg_charset)
        logging.debug("from is %s" % msg_from)

        msg_to = get_message_header(message['To'], default=msg_charset)
        logging.debug("to is %s" % msg_to)

        msg_date = email.utils.parsedate(message['Date'])
        logging.debug("date is %s" % str(msg_date))

        msg_body = get_message_body(message)
        logging.debug("body is %s" % msg_body)

        relative_str = msg_to.split("@", 1)[0]

        if msg_date:
            curdate = date.fromtimestamp(time.mktime(msg_date))
        else:
            curdate = datetime.now() if config['time_separator'] in relative_str else date.today()

        final_date = get_date_by_relative_str(curdate, relative_str)

        logging.debug("calculated datetime is %s" % str(final_date))

        timestamp_str = format_as_org_datetime(final_date) if final_date else ""
        timestamp_str = config['timestamp_layout'].format(timestamp=timestamp_str)

        msg_body = indent(remove_signature(msg_body[:1000].replace('\r', '')), "")

        content_data = dict({'from': msg_from, 'to': msg_to, 'date': message['Date'], 'subject': msg_subject,
                             'body': msg_body})
        content_str = config['content_layout'].format(**content_data)

        org_data = dict({'subject': msg_subject, 'timestamp': timestamp_str, 'content': content_str})
        org_str = config['org_entry_layout'].format(**org_data)

        logging.debug("final org-mode entry is %s" % org_str)

    except Exception as e:
        print e

        with open("debug.txt", "a") as logfile:
            logfile.write("="*80+"\n")
            logfile.write(str(e))

        org_str = u"""* Error parsing message:\n\n%s""" % indent(messagestr[:2000], "")

    finally:

        outfile.write(org_str.encode(encoding))


def merge(opts1, opts2):
    """ merge two dicts, where opts2 overrides opts1 """
    return dict(opts1.items() + opts2.items())


if __name__ == "__main__":
    import doctest
    doctest.testmod()

    parser = argparse.ArgumentParser(description='Append email messages with special "To"-addresses to an \
                                     org-mode file.')
    parser.add_argument('-i', metavar='inputfile', type=argparse.FileType('r'),  dest='infile', action='store',
                        help='file to read the email from (default: stdin)', default='-')
    parser.add_argument('-o', metavar='outputfile', type=str,  dest='outfile', action='store',
                        help='org-mode file to write the message content to (default: stdout)')

    appendmode = parser.add_mutually_exclusive_group()
    appendmode.add_argument('--append', '-a', dest='appendmode', action='store_true', default=True,
                            help='append the org-mode entry to the given file (default: %(default)s)')
    appendmode.add_argument('--no-append', dest='appendmode', action='store_false', default=False,
                            help='overwrite the given output file (default: %(default)s)')

    parser.add_argument('--encoding', metavar='enc', type=str, dest='encoding', action='store', default='utf8',
                        help='output encoding to use, see list of available encodings at \
                        https://docs.python.org/2/library/codecs.html#standard-encodings (default: %(default)s)')

    args = parser.parse_args()

    messagestr = args.infile.read()

    logging.info('started as ' + str(sys.argv))

    if not messagestr:
        sys.exit()

    try:

        if args.outfile:
            if os.path.isfile(args.outfile):
                outfile = open(args.outfile, 'ab')
            else:
                outfile = open(args.outfile, 'wb')

        else:
            outfile = sys.stdout

        message2org(messagestr, outfile, merge(DEFAULT_CONFIG, CONFIG), encoding=args.encoding)

    finally:
        outfile.close()

        logging.info('terminated')
