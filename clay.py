#!/usr/bin/env python

from __future__ import with_statement
from string import Template
import re, fnmatch, os

VERSION = "0.7.0"

TEST_FUNC_REGEX = r"^(void\s+(test_%s__(\w+))\(\s*(void)?\s*\))\s*\{"

TEMPLATE_MAIN = Template(
r"""
/*
 * Clay v${version}
 *
 * This is an autogenerated file. Do not modify.
 * To add new unit tests or suites, regenerate the whole
 * file with `./clay`
 */

#define clay_print(...) ${clay_print}

${clay_library}

${extern_declarations}

static const struct clay_func _all_callbacks[] = {
    ${test_callbacks}
};

static const struct clay_suite _all_suites[] = {
    ${test_suites}
};

static const char _suites_str[] = "${suites_str}";

int main(int argc, char *argv[])
{
    return clay_test(
        argc, argv, _suites_str,
        _all_callbacks, ${cb_count},
        _all_suites, ${suite_count}
    );
}
""")

TEMPLATE_SUITE = Template(
r"""
    {
        "${clean_name}",
        ${initialize},
        ${cleanup},
        ${cb_ptr}, ${cb_count}
    }
""")

def main():
    from optparse import OptionParser

    parser = OptionParser()

    parser.add_option('-c', '--clay-path', dest='clay_path')
    parser.add_option('-o', '--output', dest='output')
    parser.add_option('-v', '--report-to', dest='print_mode', default='stdout')

    options, args = parser.parse_args()

    for folder in args:
        builder = ClayTestBuilder(folder,
            clay_path = options.clay_path,
            output_folder = options.output,
            print_mode = options.print_mode)

        builder.render()


class ClayTestBuilder:
    def __init__(self, folder_name, output_folder = None, clay_path = None, print_mode = 'stdout'):
        self.declarations = []
        self.callbacks = []
        self.suites = []
        self.suite_list = []

        self.clay_path = clay_path
        self.print_mode = print_mode

        folder_name = os.path.abspath(folder_name)
        if not output_folder:
            output_folder = folder_name

        self.output = os.path.join(output_folder, "clay_main.c")
        self.output_header = os.path.join(output_folder, "clay.h")

        self.modules = ["clay.c", "clay_sandbox.c"]

        print("Loading test suites...")

        for root, dirs, files in os.walk(folder_name):
            module_root = root[len(folder_name):]
            module_root = [c for c in module_root.split(os.sep) if c]

            tests_in_module = fnmatch.filter(files, "*.c")

            for test_file in tests_in_module:
                full_path = os.path.join(root, test_file)
                test_name = "_".join(module_root + [test_file[:-2]])

                with open(full_path) as f:
                    self._process_test_file(test_name, f.read())

        if not self.suites:
            raise RuntimeError(
                'No tests found under "%s"' % folder_name)

    def render(self):
        template = TEMPLATE_MAIN.substitute(
            version = VERSION,
            clay_print = self._get_print_method(),
            clay_library = self._get_library(),
            extern_declarations = "\n".join(self.declarations),

            suites_str = ", ".join(self.suite_list),

            test_callbacks = ",\n\t".join(self.callbacks),
            cb_count = len(self.callbacks),

            test_suites = ",\n\t".join(self.suites),
            suite_count = len(self.suites),
        )

        with open(self.output, "w") as out:
            out.write(template)

        with open(self.output_header, "w") as out:
            out.write(self._load_file('clay.h'))

        print ('Written test suite to "%s"' % self.output)
        print ('Written header to "%s"' % self.output_header)

    #####################################################
    # Internal methods
    #####################################################
    def _get_print_method(self):
        return {
                'stdout' : 'printf(__VA_ARGS__)',
                'stderr' : 'fprintf(stderr, __VA_ARGS__)',
                'silent' : ''
        }[self.print_mode]

    def _load_file(self, filename):
        if self.clay_path:
            filename = os.path.join(self.clay_path, filename)
            with open(filename) as cfile:
                return cfile.read()

        else:
            import zlib, base64, sys
            content = CLAY_FILES[filename]

            if sys.version_info >= (3, 0):
                content = bytearray(content, 'utf_8')
                content = base64.b64decode(content)
                content = zlib.decompress(content)
                return str(content)
            else:
                content = base64.b64decode(content)
                return zlib.decompress(content)

    def _get_library(self):
        return "\n".join(self._load_file(f) for f in self.modules)

    def _parse_comment(self, comment):
        comment = comment[2:-2]
        comment = comment.splitlines()
        comment = [line.strip() for line in comment]
        comment = "\n".join(comment)

        return comment

    def _process_test_file(self, test_name, contents):
        regex_string = TEST_FUNC_REGEX % test_name
        regex = re.compile(regex_string, re.MULTILINE)

        callbacks = []
        initialize = cleanup = "{NULL, NULL, 0}"

        for (declaration, symbol, short_name, _) in regex.findall(contents):
            self.declarations.append("extern %s;" % declaration)
            func_ptr = '{"%s", &%s, %d}' % (
                short_name, symbol, len(self.suites)
            )

            if short_name == 'initialize':
                initialize = func_ptr
            elif short_name == 'cleanup':
                cleanup = func_ptr
            else:
                callbacks.append(func_ptr)

        if not callbacks:
            return

        clean_name = test_name.replace("_", "::")

        suite = TEMPLATE_SUITE.substitute(
            clean_name = clean_name,
            initialize = initialize,
            cleanup = cleanup,
            cb_ptr = "&_all_callbacks[%d]" % len(self.callbacks),
            cb_count = len(callbacks)
        ).strip()

        self.callbacks += callbacks
        self.suites.append(suite)
        self.suite_list.append(clean_name)

        print("  %s (%d tests)" % (clean_name, len(callbacks)))

CLAY_FILES = {
"clay.c" : r"""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""",
"clay_sandbox.c" : r"""eJx9VW1P2zAQ/pz8iiNoNKEZDRvaNGX9MIkyVRSoCohJtIpC4lCLxOlst1o3+O+7S0KalJeqamLf47vnOd9dd3kSswSCm+H550/mroELLhiMRz+uTi4mZ8HlYAyd6bRj7rJUsbcAPbKLmCemqXSoeQTRPJQQRGm4Dhahnt8eed++zPzazIU2uQpWYcrjQGeLAmRHuVC6PLpPG475zzSUlstIAx3EH980JNNLKcBOacsmnAt7SjvQ74MHe3umYdiXwfDyeDixlT5QOsjymDnw+IgWMozOT5sGpzwTRhFTqvJ3E1yclg4d33xq0Ub5TcoF2btlkjDpguJ/WaAhZeK+Zl+mo1BWmVehDKJ8KTT04cjfwpQOmVhhcqS6nSEG3RjW1dkYBVku0FvxGJTP68vBZDy5OBmOBpYJxhMmGYwqEsfFbuuGDZ6A/ZPpK5YtxiTAPr65mBw7JWUXSiWOgyGrPB/69d0aSS7B5kjJ84HD940SH7pd7hRMt2Qg+J5pfLFrTXyGSTUKJju4SbHolOZiyZBwaXlZHQQtQ1BNiGixtp/zjib3OevkusHdMJ5M/JpGbx+GCeg5IzSXucgY3kCcMyU6eDXhGkKx1nMu7l3Qcg06h6Vi0MP4sN8z3yBlkd2qeG3TKo0tZg1iFamrOVeg1kqzrGaT8geG0VtEiHm0lLJgzSWLdI7Gd5gdvEnr4F1O1dLbKnyIUhaKIMnTmMnXW7WxmasgymIq3+0CNCwZQ09B7zdMrQ9qall+NVzIlMFHmTQNVeUVTqM8y0IRPw8TQ4mFRGaJXRnKBszrteNWPFwoOG6GR5nvGteUusp5DMXgWgqFxrv8j017hUJKdWOqeTOaEZ2p19k0DFVwK1Ub/PYsKcO8CNJII50KdMjTYhBYBZ5u+FfxsSgH9cihwEVPtSfUJnydngajZqd75AEdYSQsGXxpU3+hnqAf4XAGO/3W/0FZdW1gt0sCmqiq2jAS1eYGDV0S426k16GzB7yzRZMUZf/8ejTaFlGisUta6r2vnucQWe81fDRv419HbnoFyf8Hmxc92w==""",
"clay.h" : r"""eJy9lF9PwjAUxZ/Zp7huLxtZCL4ikhgDkYT4IonxqSntnTTWdvaP4re33TA6HCG+8LTb2/b+zjnZlolKcayAkNvVzRNZzx/W5I6QJAtNofBPP8mEYtJzhKl1XIrNaDtLknctODBJPwmh1qJxeTIQygHTigsntCqTQaht6GypgWElJJbtERkoB7tojDYHPY6WGVHvZ8WLdqu95IRutHHF1W8NFh1hEqnydd508+F+WbTrYVFCW+iavnmM178NNxNevXWkDlZy3NWmhEgvugabnQJm1zAuQ0qL5WpOSKxWy/umShdesagXGJUSKho88wmkkP3MLOGy6CHHsyfJ06Pg+a5G5pBD1VHgdCPipIQ95hT/4rjzIMCgtZEsLCjtwBmPfeAumW2RvZwn93HRhz5v8L0azpD7+DD3xnYP8RhnjeG7bIMdpcdeow9qlFDP/5n72F4B7k18uIjBHTIfs5ykHf0Y/ixV8gUUh4yr"""
}

if __name__ == '__main__':
    main()



