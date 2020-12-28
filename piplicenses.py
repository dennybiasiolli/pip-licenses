#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et
"""
pip-licenses

MIT License

Copyright (c) 2018 raimon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import argparse
import codecs
import glob
import os
import sys
from collections import Counter
from email import message_from_string
from email.parser import FeedParser
from functools import partial

try:
    from pip._internal.utils.misc import get_installed_distributions
except ImportError:  # pragma: no cover
    from pip import get_installed_distributions
from prettytable import PrettyTable
try:
    from prettytable.prettytable import (
        ALL as RULE_ALL,
        FRAME as RULE_FRAME,
        HEADER as RULE_HEADER,
        NONE as RULE_NONE,
    )
    PTABLE = True
except ImportError:  # pragma: no cover
    from prettytable import (
        ALL as RULE_ALL,
        FRAME as RULE_FRAME,
        HEADER as RULE_HEADER,
        NONE as RULE_NONE,
    )
    PTABLE = False

open = open  # allow monkey patching

__pkgname__ = 'pip-licenses'
__version__ = '3.1.0'
__author__ = 'raimon'
__license__ = 'MIT'
__summary__ = ('Dump the software license list of '
               'Python packages installed with pip.')
__url__ = 'https://github.com/raimon49/pip-licenses'


FIELD_NAMES = (
    'Name',
    'Version',
    'License',
    'LicenseFile',
    'LicenseText',
    'NoticeFile',
    'NoticeText',
    'Author',
    'Description',
    'URL',
)


SUMMARY_FIELD_NAMES = (
    'Count',
    'License',
)


DEFAULT_OUTPUT_FIELDS = (
    'Name',
    'Version',
)


SUMMARY_OUTPUT_FIELDS = (
    'Count',
    'License',
)


METADATA_KEYS = (
    'home-page',
    'author',
    'license',
    'summary',
    'license_classifier',
)

# Mapping of FIELD_NAMES to METADATA_KEYS where they differ by more than case
FIELDS_TO_METADATA_KEYS = {
    'URL': 'home-page',
    'Description': 'summary',
    'License-Metadata': 'license',
    'License-Classifier': 'license_classifier',
}


SYSTEM_PACKAGES = (
    __pkgname__,
    'pip',
    'PTable' if PTABLE else 'prettytable',
    'setuptools',
    'wheel',
)

LICENSE_UNKNOWN = 'UNKNOWN'


def get_packages(args):

    def get_pkg_included_file(pkg, file_names):
        """
        Attempt to find the package's included file on disk and return the
        tuple (included_file_path, included_file_contents).
        """
        included_file = LICENSE_UNKNOWN
        included_text = LICENSE_UNKNOWN
        pkg_dirname = "{}-{}.dist-info".format(
            pkg.project_name.replace("-", "_"), pkg.version)
        patterns = []
        [patterns.extend(sorted(glob.glob(os.path.join(pkg.location,
                                                       pkg_dirname,
                                                       f))))
         for f in file_names]
        for test_file in patterns:
            if os.path.exists(test_file):
                included_file = test_file
                with open(test_file, encoding='utf-8',
                          errors='backslashreplace') as included_file_handle:
                    included_text = included_file_handle.read()
                break
        return (included_file, included_text)

    def get_pkg_info(pkg):
        (license_file, license_text) = get_pkg_included_file(
            pkg,
            ('LICENSE*', 'LICENCE*', 'COPYING*')
        )
        (notice_file, notice_text) = get_pkg_included_file(
            pkg,
            ('NOTICE*',)
        )
        pkg_info = {
            'name': pkg.project_name,
            'version': pkg.version,
            'namever': str(pkg),
            'licensefile': license_file,
            'licensetext': license_text,
            'noticefile': notice_file,
            'noticetext': notice_text,
        }
        metadata = None
        if pkg.has_metadata('METADATA'):
            metadata = pkg.get_metadata('METADATA')

        if pkg.has_metadata('PKG-INFO') and metadata is None:
            metadata = pkg.get_metadata('PKG-INFO')

        if metadata is None:
            for key in METADATA_KEYS:
                pkg_info[key] = LICENSE_UNKNOWN

            return pkg_info

        feed_parser = FeedParser()
        feed_parser.feed(metadata)
        parsed_metadata = feed_parser.close()

        for key in METADATA_KEYS:
            pkg_info[key] = parsed_metadata.get(key, LICENSE_UNKNOWN)

        if metadata is not None:
            message = message_from_string(metadata)
            pkg_info['license_classifier'] = \
                find_license_from_classifier(message)

        if args.filter_strings:
            for k in pkg_info:
                if isinstance(pkg_info[k], list):
                    for i, item in enumerate(pkg_info[k]):
                        pkg_info[k][i] = item. \
                            encode(args.filter_code_page, errors="ignore"). \
                            decode(args.filter_code_page)
                else:
                    pkg_info[k] = pkg_info[k]. \
                        encode(args.filter_code_page, errors="ignore"). \
                        decode(args.filter_code_page)

        return pkg_info

    pkgs = get_installed_distributions()
    ignore_pkgs_as_lower = [pkg.lower() for pkg in args.ignore_packages]

    fail_on_licenses = None
    if args.fail_on:
        fail_on_licenses = args.fail_on.split(";")

    allow_only_licenses = None
    if args.allow_only:
        allow_only_licenses = args.allow_only.split(";")

    for pkg in pkgs:
        pkg_name = pkg.project_name

        if pkg_name.lower() in ignore_pkgs_as_lower:
            continue

        if not args.with_system and pkg_name in SYSTEM_PACKAGES:
            continue

        pkg_info = get_pkg_info(pkg)

        license_name = select_license_by_source(
            getattr(args, 'from'),
            pkg_info['license_classifier'],
            pkg_info['license'])

        if fail_on_licenses and license_name in fail_on_licenses:
            sys.stderr.write("fail-on license {} was found for package "
                             "{}:{}".format(
                                license_name,
                                pkg_info['name'],
                                pkg_info['version'])
                             )
            sys.exit(1)

        if allow_only_licenses and license_name not in allow_only_licenses:
            sys.stderr.write("license {} not in allow-only licenses was found"
                             " for package {}:{}".format(
                                license_name,
                                pkg_info['name'],
                                pkg_info['version'])
                             )
            sys.exit(1)

        yield pkg_info


def create_licenses_table(args, output_fields=DEFAULT_OUTPUT_FIELDS):
    table = factory_styled_table_with_args(args, output_fields)
    from_source = getattr(args, 'from')

    for pkg in get_packages(args):
        row = []
        for field in output_fields:
            if field == 'License':
                license_str = select_license_by_source(
                    from_source, pkg['license_classifier'], pkg['license'])
                row.append(license_str)
            elif field == 'License-Classifier':
                row.append(', '.join(pkg['license_classifier'])
                           or LICENSE_UNKNOWN)
            elif field.lower() in pkg:
                row.append(pkg[field.lower()])
            else:
                row.append(pkg[FIELDS_TO_METADATA_KEYS[field]])
        table.add_row(row)

    return table


def create_summary_table(args):
    counts = Counter(pkg['license'] for pkg in get_packages(args))

    table = factory_styled_table_with_args(args, SUMMARY_FIELD_NAMES)
    for license, count in counts.items():
        table.add_row([count, license])
    return table


class JsonPrettyTable(PrettyTable):
    """PrettyTable-like class exporting to JSON"""

    def _format_row(self, row, options):
        resrow = {}
        for (field, value) in zip(self._field_names, row):
            if field not in options["fields"]:
                continue

            resrow[field] = value

        return resrow

    def get_string(self, **kwargs):
        # import included here in order to limit dependencies
        # if not interested in JSON output,
        # then the dependency is not required
        import json

        options = self._get_options(kwargs)
        rows = self._get_rows(options)
        formatted_rows = self._format_rows(rows, options)

        lines = []
        for row in formatted_rows:
            lines.append(row)

        return json.dumps(lines, indent=2, sort_keys=True)


class JsonLicenseFinderTable(JsonPrettyTable):
    def _format_row(self, row, options):
        resrow = {}
        for (field, value) in zip(self._field_names, row):
            if field == 'Name':
                resrow['name'] = value

            if field == 'Version':
                resrow['version'] = value

            if field == 'License':
                resrow['licenses'] = [value]

        return resrow

    def get_string(self, **kwargs):
        # import included here in order to limit dependencies
        # if not interested in JSON output,
        # then the dependency is not required
        import json

        options = self._get_options(kwargs)
        rows = self._get_rows(options)
        formatted_rows = self._format_rows(rows, options)

        lines = []
        for row in formatted_rows:
            lines.append(row)

        return json.dumps(lines, sort_keys=True)


class CSVPrettyTable(PrettyTable):
    """PrettyTable-like class exporting to CSV"""

    def get_string(self, **kwargs):

        def esc_quotes(val):
            """
            Meta-escaping double quotes
            https://tools.ietf.org/html/rfc4180
            """
            try:
                return val.replace('"', '""')
            except UnicodeDecodeError:  # pragma: no cover
                return val.decode('utf-8').replace('"', '""')
            except UnicodeEncodeError:  # pragma: no cover
                return val.encode('unicode_escape').replace('"', '""')

        options = self._get_options(kwargs)
        rows = self._get_rows(options)
        formatted_rows = self._format_rows(rows, options)

        lines = []
        formatted_header = ','.join(['"%s"' % (esc_quotes(val), )
                                     for val in self._field_names])
        lines.append(formatted_header)
        for row in formatted_rows:
            formatted_row = ','.join(['"%s"' % (esc_quotes(val), )
                                      for val in row])
            lines.append(formatted_row)

        return '\n'.join(lines)


class PlainVerticalTable(PrettyTable):
    """PrettyTable for outputting to a simple non-column based style.

    When used with --with-license-file, this style is similar to the default
    style generated from Angular CLI's --extractLicenses flag.
    """

    def get_string(self, **kwargs):
        options = self._get_options(kwargs)
        rows = self._get_rows(options)

        output = ''
        for row in rows:
            for v in row:
                output += '{}\n'.format(v)
            output += '\n'

        return output


def factory_styled_table_with_args(args, output_fields=DEFAULT_OUTPUT_FIELDS):
    table = PrettyTable()
    table.field_names = output_fields
    table.align = 'l'
    table.border = (args.format == 'markdown' or args.format == 'rst' or
                    args.format == 'confluence' or args.format == 'json')
    table.header = True

    if args.format == 'markdown':
        table.junction_char = '|'
        table.hrules = RULE_HEADER
    elif args.format == 'rst':
        table.junction_char = '+'
        table.hrules = RULE_ALL
    elif args.format == 'confluence':
        table.junction_char = '|'
        table.hrules = RULE_NONE
    elif args.format == 'json':
        table = JsonPrettyTable(table.field_names)
    elif args.format == 'json-license-finder':
        table = JsonLicenseFinderTable(table.field_names)
    elif args.format == 'csv':
        table = CSVPrettyTable(table.field_names)
    elif args.format == 'plain-vertical':
        table = PlainVerticalTable(table.field_names)

    return table


def find_license_from_classifier(message):
    licenses = []
    for k, v in message.items():
        if k == 'Classifier' and v.startswith('License'):
            license = v.split(' :: ')[-1]

            # Through the declaration of 'Classifier: License :: OSI Approved'
            if license != 'OSI Approved':
                licenses.append(license)

    return licenses


def select_license_by_source(from_source, license_classifier, license_meta):
    license_classifier_str = ', '.join(license_classifier) or LICENSE_UNKNOWN
    if (from_source == 'classifier' or
            from_source == 'mixed' and len(license_classifier) > 0):
        return license_classifier_str
    else:
        return license_meta


def get_output_fields(args):
    if args.summary:
        return list(SUMMARY_OUTPUT_FIELDS)

    output_fields = list(DEFAULT_OUTPUT_FIELDS)

    if getattr(args, 'from') == 'all':
        output_fields.append('License-Metadata')
        output_fields.append('License-Classifier')
    else:
        output_fields.append('License')

    if args.with_authors:
        output_fields.append('Author')

    if args.with_urls:
        output_fields.append('URL')

    if args.with_description:
        output_fields.append('Description')

    if args.with_license_file:
        if not args.no_license_path:
            output_fields.append('LicenseFile')

        output_fields.append('LicenseText')

        if args.with_notice_file:
            output_fields.append('NoticeText')
            if not args.no_license_path:
                output_fields.append('NoticeFile')

    return output_fields


def get_sortby(args):
    if args.summary and args.order == 'count':
        return 'Count'
    elif args.summary or args.order == 'license':
        return 'License'
    elif args.order == 'name':
        return 'Name'
    elif args.order == 'author' and args.with_authors:
        return 'Author'
    elif args.order == 'url' and args.with_urls:
        return 'URL'

    return 'Name'


def create_output_string(args):
    output_fields = get_output_fields(args)

    if args.summary:
        table = create_summary_table(args)
    else:
        table = create_licenses_table(args, output_fields)

    sortby = get_sortby(args)

    if args.format == 'html':
        return table.get_html_string(fields=output_fields, sortby=sortby)
    else:
        return table.get_string(fields=output_fields, sortby=sortby)


def create_warn_string(args):
    warn_messages = []
    warn = partial(output_colored, '33')

    if args.with_license_file and not args.format == 'json':
        message = warn(('Due to the length of these fields, this option is '
                        'best paired with --format=json.'))
        warn_messages.append(message)

    if args.summary and (args.with_authors or args.with_urls):
        message = warn(('When using this option, only --order=count or '
                        '--order=license has an effect for the --order '
                        'option. And using --with-authors and --with-urls '
                        'will be ignored.'))
        warn_messages.append(message)

    return '\n'.join(warn_messages)


class CompatibleArgumentParser(argparse.ArgumentParser):

    def parse_args(self, args=None, namespace=None):
        args = super(CompatibleArgumentParser, self).parse_args(args,
                                                                namespace)
        self._compatible_format_args(args)
        self._check_code_page(args.filter_code_page)

        return args

    @staticmethod
    def _check_code_page(code_page):
        try:
            codecs.lookup(code_page)
        except LookupError:
            print(("error: invalid code page '%s' given for "
                   "--filter-code-page;\n"
                   "       check https://docs.python.org/3/library/"
                   "codecs.html for valid code pages") % code_page)
            sys.exit(1)

    @staticmethod
    def _compatible_format_args(args):
        from_input = getattr(args, 'from').lower()
        order_input = args.order.lower()
        format_input = args.format.lower()

        # XXX: Use enum when drop support Python 2.7
        if from_input in ('meta', 'm'):
            setattr(args, 'from', 'meta')

        if from_input in ('classifier', 'c'):
            setattr(args, 'from', 'classifier')

        if from_input in ('mixed', 'mix'):
            setattr(args, 'from', 'mixed')

        if order_input in ('count', 'c'):
            args.order = 'count'

        if order_input in ('license', 'l'):
            args.order = 'license'

        if order_input in ('name', 'n'):
            args.order = 'name'

        if order_input in ('author', 'a'):
            args.order = 'author'

        if order_input in ('url', 'u'):
            args.order = 'url'

        if format_input in ('plain', 'p'):
            args.format = 'plain'

        if format_input in ('markdown', 'md', 'm'):
            args.format = 'markdown'

        if format_input in ('rst', 'rest', 'r'):
            args.format = 'rst'

        if format_input in ('confluence', 'c'):
            args.format = 'confluence'

        if format_input in ('html', 'h'):
            args.format = 'html'

        if format_input in ('json', 'j'):
            args.format = 'json'

        if format_input in ('json-license-finder', 'jlf'):
            args.format = 'json-license-finder'

        if format_input in ('csv', ):
            args.format = 'csv'


def create_parser():
    parser = CompatibleArgumentParser(
        description=__summary__)
    parser.add_argument('-v', '--version',
                        action='version',
                        version='%(prog)s ' + __version__)
    parser.add_argument('--from',
                        action='store', type=str,
                        default='mixed', metavar='SOURCE',
                        help=('where to find license information\n'
                              '"meta", "classifier, "mixed", "all"\n'
                              'default: --from=mixed'))
    parser.add_argument('-s', '--with-system',
                        action='store_true',
                        default=False,
                        help='dump with system packages')
    parser.add_argument('-a', '--with-authors',
                        action='store_true',
                        default=False,
                        help='dump with package authors')
    parser.add_argument('-u', '--with-urls',
                        action='store_true',
                        default=False,
                        help='dump with package urls')
    parser.add_argument('-d', '--with-description',
                        action='store_true',
                        default=False,
                        help='dump with short package description')
    parser.add_argument('-l', '--with-license-file',
                        action='store_true',
                        default=False,
                        help='dump with location of license file and '
                             'contents, most useful with JSON output')
    parser.add_argument('--no-license-path',
                        action='store_true',
                        default=False,
                        help='when specified together with option -l, '
                             'suppress location of license file output')
    parser.add_argument('--with-notice-file',
                        action='store_true',
                        default=False,
                        help='when specified together with option -l, '
                             'dump with location of license file and contents')
    parser.add_argument('-i', '--ignore-packages',
                        action='store', type=str,
                        nargs='+', metavar='PKG',
                        default=[],
                        help='ignore package name in dumped list')
    parser.add_argument('-o', '--order',
                        action='store', type=str,
                        default='name', metavar='COL',
                        help=('order by column\n'
                              '"name", "license", "author", "url"\n'
                              'default: --order=name'))
    parser.add_argument('-f', '--format',
                        action='store', type=str,
                        default='plain', metavar='STYLE',
                        help=('dump as set format style\n'
                              '"plain", "plain-vertical" "markdown", "rst", \n'
                              '"confluence", "html", "json", \n'
                              '"json-license-finder",  "csv"\n'
                              'default: --format=plain'))
    parser.add_argument('--filter-strings',
                        action="store_true",
                        default=False,
                        help=('filter input according to code page'))
    parser.add_argument('--filter-code-page',
                        action="store", type=str,
                        default="latin1",
                        help=('specify code page for filtering'))
    parser.add_argument('--summary',
                        action='store_true',
                        default=False,
                        help='dump summary of each license')
    parser.add_argument('--output-file',
                        action='store', type=str,
                        help='save license list to file')
    parser.add_argument('--fail-on',
                        action='store', type=str,
                        default=None,
                        help='fail (exit with code 1) on the first occurrence '
                             'of the licenses of the semicolon-separated list')
    parser.add_argument('--allow-only',
                        action='store', type=str,
                        default=None,
                        help='fail (exit with code 1) on the first occurrence '
                             'of the licenses not in the semicolon-separated '
                             'list')

    return parser


def output_colored(code, text, is_bold=False):
    """
    Create function to output with color sequence
    """
    if is_bold:
        code = '1;%s' % code

    return '\033[%sm%s\033[0m' % (code, text)


def save_if_needs(output_file, output_string):
    """
    Save to path given by args
    """
    if output_file is None:
        return

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_string)
        sys.stdout.write('created path: ' + output_file + '\n')
        sys.exit(0)
    except IOError:
        sys.stderr.write('check path: --output-file\n')
        sys.exit(1)


def main():  # pragma: no cover
    parser = create_parser()
    args = parser.parse_args()

    output_string = create_output_string(args)

    output_file = args.output_file
    save_if_needs(output_file, output_string)

    print(output_string)
    warn_string = create_warn_string(args)
    if warn_string:
        print(warn_string, file=sys.stderr)


if __name__ == '__main__':  # pragma: no cover
    main()
