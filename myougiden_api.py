#!/usr/bin/python
import argparse
import sys
import re
import romkan

from myougiden import config
from myougiden import color
from myougiden import database
from myougiden import orm
from myougiden import common
from myougiden import texttools as tt
from myougiden import search
from myougiden.color import fmt

def run(query):
	ap = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)

	ap.add_argument('--version', action='store_true',
		            help='Show version.')

	ag = ap.add_argument_group('Type of query',
		                       '''What field to look in.  If not provided, try all of them and return the
	first to match.''')
	ag.add_argument('-k', '--kanji', action='store_const', dest='field', const='kanji', default='auto',
		            help='''Return entries matching query on kanji.''')

	ag.add_argument('-r', '--reading', action='store_const', dest='field', const='reading',
		            help='''Return entries matching query on reading (in kana or rōmaji).''')

	ag.add_argument('-g', '--gloss', '--meaning', action='store_const', dest='field', const='gloss',
		            help='''Return entries matching query on glosses (English
	translations/meaning).''')


	ag = ap.add_argument_group('Query options')
	ag.add_argument('--case-sensitive', '--sensitive', action='store_true',
		            help='''Case-sensitive search (distinguish uppercase from
	lowercase). Default: Insensitive, unless there's an
	uppercase letter in query.''')

	ag.add_argument('-x', '--regexp', action='store_true',
		            help='''Regular expression search.  Extent limits (-e) are
	respected.  Regexps currently don't work for rōmaji;
	use kana for readings.''')

	ag.add_argument('-e', '--extent', default='auto',
		            choices=('whole', 'beginning', 'word', 'partial', 'auto'),
		            help='''How much of the field should the query match:
	 - whole: Query must match the entire field.
	 - beginning: Query must match the beginning of the field.
	 - word: Query must match whole word (at present
	   only works for English; treated as 'whole' for
	   kanji or reading fields.)
	 - partial: Query may match anywhere, even partially
	   inside words.
	 - auto (default): Try all four, and return the
	   first to match something.''')

	ag.add_argument('-w', '--whole', action='store_const', const='whole', dest='extent',
		            help='''Equivalent to --extent=whole.''')

	ag.add_argument('-b', '--beginning', action='store_const', const='beginning', dest='extent',
		            help='''Equivalent to --extent=beginning.''')

	ag.add_argument('--word', action='store_const', const='word', dest='extent',
		            help='''Equivalent to --extent=word.''')

	ag.add_argument('-p', '--partial', action='store_const', const='partial', dest='extent',
		            help='Equivalent to --extent=partial.')
	ag.add_argument('-f', '--frequent', '-P', action='store_true',
		            help='''Restrict to frequent words (equivalent to EDICT
	entries marked as ‘(P)’)''')



	ag = ap.add_argument_group('Output control')
	ag.add_argument('--output-mode', default='tab', choices=('human', 'tab', 'auto'),
		            help='''Output mode; one of:
	 - human: Multiline human-readable output.
	 - tab: One-line tab-separated.
	 - auto (default): Human if output is to terminal,
	tab if writing to pipe or file.''')

	ag.add_argument('-t', '--tsv', '--tab', action='store_const', const='tab', dest='output_mode',
		            help="Equivalent to --output-mode=tab")

	ag.add_argument('--human', action='store_const', const='human', dest='output_mode',
		            help="Equivalent to --output-mode=human")
	ag.add_argument('--color', choices=('yes', 'no', 'auto'), default='no',
		            help='''Whether to colorize output.  Default 'auto' means to
	colorize if writing to a terminal.''')
	ag.add_argument('-c', action='store_const', const='yes', dest='color',
		            help='Equivalent to --color=yes')
	ag.add_argument('--background', '--bg', choices=('dark', 'light', 'auto'), default='auto',
		            help='''Use colorscheme for dark or light background.
	Autodetection can be spotty.  If it's not working for you, you can also set it
	in the BACKGROUND environment variable.''')

	ag.add_argument('--out-hepburn', '--oh',
		            action='store_const', const=romkan.to_hepburn,
		            dest='out_romaji', default=None,
		            help='Convert reading to Hepburn rōmaji in output.')
	ag.add_argument('--out-kunrei', '--ok',
		            action='store_const', const=romkan.to_kunrei,
		            dest='out_romaji', default=None,
		            help='Convert reading to Kunrei rōmaji in output.')

	ag = ap.add_argument_group('Abbreviations help')
	ag.add_argument('--list-abbrevs', action='store_true',
		    help='''List all abbreviations.''')
	ag.add_argument('-a', '--abbrev', metavar='ABBREV', default=None,
		    help='''Print meaning of an abbreviation.''')


	ap.add_argument('query', help='Text to look for.', metavar='QUERY', nargs='*')


	args = ap.parse_args()
	args.output_mode = 'tab'
	args.query = query
	args.color = 'no'

	# handle output guesswork.
	if args.output_mode == 'auto':
		if sys.stdout.isatty():
		    args.output_mode = 'human'
		else:
		    args.output_mode = 'tab'

	if args.color == 'auto':
		if sys.stdout.isatty():
		    args.color = 'yes'
		else:
		    args.color = 'no'

	color.use_color =  (args.color == 'yes')
	if color.use_color:
		if args.background == 'auto':
		    args.background = color.guess_background() or 'dark'

		if args.background == 'dark':
		    pass # default
		else:
		    color.style = color.LIGHTBG

	args.query = ' '.join(args.query)

	# case sensitivity must be handled before opening db
	if not args.case_sensitive:
		if re.search("[A-Z]", args.query):
		    args.case_sensitive = True

	if not config:
		print('%s: Could not find config.ini!' % fmt('ERROR', 'error'))

		# print version regardless
		if args.version:
		    print(common.version(None))
		sys.exit(2)

	# try to open database
	try:
		con, cur = database.opendb(case_sensitive=args.case_sensitive)
	except database.DatabaseAccessError as e:
		print('''Database error: %s.
	Expected database version %s at:
	%s

	Before using myougiden for the first time, you need to compile the JMdict
	(EDICT) dictionary.  Try running this command to download and compile it:

		updatedb-myougiden -f

	It will take a while, but lookups afterwards will be fast.

	JMdict is frequently updated.  If you'd like to keep up with new entries,
	you might want to add the update command to cron (for example, in
	/etc/cron.weekly/myougiden ).'''
		% (str(e), config.get('core','dbversion'), config.get('paths','database')))

		if args.version:
		    print()
		    print(common.version(None))
		sys.exit(2)


	# handle short commands first.
	if args.version:
		print(common.version(cur))
		sys.exit(0)

	elif args.list_abbrevs:
		print(orm.abbrevs_table(cur))
		sys.exit(0)

	elif args.abbrev:
		a = orm.abbrev_line(cur, args.abbrev)
		if a:
		    print(a)
		    sys.exit(0)
		else:
		    print('Not found!')
		    sys.exit(0)

	# handle query guesswork
	if args.query == '':
		ap.print_help()
		sys.exit(2)

	# 'word' doesn't work for Jap. anyway, and 'whole' is much faster.
	if args.extent == 'word' and args.field in ('kanji', 'reading'):
		args.extent = 'whole'


	# first, we need a dictionary of options with only keys understood
	# by search_by().
	search_args = vars(args).copy() # turn Namespace to dict
	# keep only interesting keys
	for k in list(search_args.keys()):
		if k not in ('field', 'query', 'extent', 'regexp', 'case_sensitive', 'frequent'):
		    del search_args[k]

	# we'll iterate over all required 'field' and 'extent' conditions.
	#
	# for code clarity, we always use a list of search conditions,
	# even if the size of the list is 1.

	if args.field == 'auto':
		if tt.is_latin(args.query):
		    # if pure alphabet, try as English first, then as rōmaji
		    fields = ('gloss', 'reading', 'kanji')
		elif tt.is_romaji(args.query):
		    # latin with special chars; probably rōmaji
		    fields = ('reading', 'gloss', 'kanji')
		elif tt.is_kana(args.query):
		    fields = ('reading', 'kanji', 'gloss')
		else:
		    fields = ('kanji', 'reading', 'gloss')
	else:
		fields = (args.field,)

	if args.extent != 'auto':
		extents = (args.extent,)
	else:
		extents = ('whole', 'word', 'partial')

	if args.regexp:
		regexp_flags = (True,)
	elif tt.has_regexp_special(args.query):
		regexp_flags = (False, True)
	else:
		regexp_flags = (False,)

	conditions = []
	for regexp in regexp_flags:
		for extent in extents:
		    for field in fields:

		        # the useless combination; we'll avoid it to avoid wasting
		        # time.
		        if extent == 'word' and field != 'gloss':

		            if args.extent == 'auto':
		                # we're trying all possibilities, so we can just
		                # skip this one.  other extents were/will be tried
		                # elsewhen in the loop.
		                continue
		            else:
		                # not trying all possibilities; this is our only
		                # pass in this field, so let's adjust it.
		                sa = search_args.copy()
		                sa['extent'] = 'whole'
		        else:
		            # simple case.
		            sa = search_args.copy()
		            sa['extent'] = extent

		        sa['field'] = field
		        sa['regexp'] = regexp

		        conditions.append(sa)

	# deal with rōmaji queries
	if (args.field in ('auto', 'reading') and tt.is_romaji(args.query)):

		if re.search('[A-Z]', args.query):
		    kana_guess=(romkan.to_katakana, romkan.to_hiragana)
		else:
		    kana_guess=(romkan.to_hiragana, romkan.to_katakana)

		new_conditions = conditions[:]
		for oldcond in conditions:
		    if oldcond['field'] == 'reading':
		        for kanafn in kana_guess:
		            # the query looks like romaji and the field is reading.
		            # so we try it converted to kana _first_, then try as-is.
		            # thus the insert.

		            for romaji in tt.expand_romaji(oldcond['query']):
		                newcond = oldcond.copy()
		                newcond['query'] = kanafn(romaji)
		                new_conditions.insert(new_conditions.index(oldcond),
		                                      newcond)
		conditions = new_conditions


	chosen_search, ent_seqs = search.guess(cur, conditions)

	if chosen_search:
		entries = [orm.fetch_entry(cur, ent_seq) for ent_seq in ent_seqs]

		if args.output_mode == 'human':
		    out = [ entry.format_human(search_params=chosen_search,
		                                  romajifn=args.out_romaji)
		              for entry in entries]

		    out = ("\n\n".join(out)) + "\n"

		elif args.output_mode == 'tab':
		    out = [ entry.format_tsv(search_params=chosen_search,
		                             romajifn=args.out_romaji)
		           for entry in entries]

		    #out = ("\n".join(out)) + "\n"

		if sys.stdout.isatty():
		    pager = common.color_pager()
		    if pager:
		        if out.count("\n") > common.get_terminal_size()[1]:
		            import subprocess
		            import shlex
		            p = subprocess.Popen(shlex.split(pager), stdin=subprocess.PIPE)
		            p.communicate(out.encode())
		            p.wait()
		            sys.exit(0)

		return out
	else:
		return None
