import sublime
import sublime_plugin
import re
from functools import reduce

def escape(str):
    return str.replace('$', '\$').replace('{', '\{').replace('}', '\}')

def getParser(view):
    scope = view.scope_name(view.sel()[0].end())
    res = re.search('\\bsource\\.([a-z+\-]+)', scope)
    sourceLang = res.group(1) if res else 'lua'
    viewSettings = view.settings()

    if sourceLang == "lua":
        return DocsLua(viewSettings)
    return DocsLua(viewSettings)

def read_line(view, point):
    if (point >= view.size()):
        return

    next_line = view.line(point)
    return view.substr(next_line)

def counter():
    count = 0
    while True:
        count += 1
        yield(count)

def splitByCommas(str):
    """
    Split a string by unenclosed commas: that is, commas which are not inside of quotes or brackets.
    splitByCommas('foo, bar(baz, quux), fwip = "hey, hi"')
     ==> ['foo', 'bar(baz, quux)', 'fwip = "hey, hi"']
    """
    out = []

    if not str:
        return out

    # the current token
    current = ''

    # characters which open a section inside which commas are not separators between different arguments
    openQuotes = '"\'<({'
    # characters which close the section. The position of the character here should match the opening
    # indicator in `openQuotes`
    closeQuotes = '"\'>)}'

    matchingQuote = ''
    insideQuotes = False
    nextIsLiteral = False

    for char in str:
        if nextIsLiteral:  # previous char was a \
            current += char
            nextIsLiteral = False
        elif insideQuotes:
            if char == '\\':
                nextIsLiteral = True
            else:
                current += char
                if char == matchingQuote:
                    insideQuotes = False
        else:
            if char == ',':
                out.append(current.strip())
                current = ''
            else:
                current += char
                quoteIndex = openQuotes.find(char)
                if quoteIndex > -1:
                    matchingQuote = closeQuotes[quoteIndex]
                    insideQuotes = True

    out.append(current.strip())
    return out

def write(view, str):
    view.run_command(
        'insert_snippet', {
            'contents': str
        }
    )

class LuaDocsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.initialize(self.view)

        #清除焦点后边文字
        self.view.erase(edit, self.trailingRgn)

        if self.line:
            out = self.parse(self.line)
            if (out):
                snippet = self.createSnippet(out)
                write(self.view, snippet)

    def initialize(self, v):
        #获取鼠标焦点位置
        point = v.sel()[0].end()
        self.settings = v.settings()

        self.trailingRgn = sublime.Region(point, v.line(point).end())

        scope = v.scope_name(v.sel()[0].end())
        res = re.search('\\bsource\\.([a-z+\-]+)', scope)
        sourceLang = res.group(1) if res else 'lua'
        viewSettings = v.settings()

        if sourceLang == "lua":
            self.line = self.getNextLine(v, v.line(point).end() + 1)

    def createSnippet(self, out):
        maxLineWidth = self.calMaxParam(out) + 2
        snippet = ""

        index = 1

        if len(out) > 1:
            if out:
                snippet += "--[["
                for line in out:
                    snippet += "\n  " + line if line else ""
                    if line.startswith('@'):
                        index += index
                        snippetLen = len(line)
                        snippet += (maxLineWidth-snippetLen) * " "
                        snippet += "${%s:desc}" % index

            snippet += "\n" + "]]"
        else:
            snippet += "-- " + out[0]

        return snippet

    #计算参数的最大长度
    def calMaxParam(self, out):
        maxLen = 0
        for line in out:
            if line.startswith('@'):
                maxLen = max(maxLen, len(line))
        return maxLen

    def getNextLine(self, view, pos):
        maxLines = 25  # don't go further than this
        openBrackets = 0

        definition = ''

        # count the number of open parentheses
        def countBrackets(total, bracket):
            return total + (1 if bracket == '(' else -1)

        for i in range(0, maxLines):
            line = read_line(view, pos)
            if line is None:
                break

            pos += len(line) + 1
            # strip comments
            line = re.sub(r"//.*",     "", line)
            line = re.sub(r"/\*.*\*/", "", line)

            searchForBrackets = line

            # on the first line, only start looking from *after* the actual function starts. This is
            # needed for cases like this:
            # (function (foo, bar) { ... })
            identifier = '[a-zA-Z_][a-zA-Z0-9_]*'
            fnOpener = '(?:' + r'function[\s*]*(?:' + identifier + r')?\s*\(' + '|' + '(?:' + identifier + r'|\(.*\)\s*=>)' + '|' + '(?:' + identifier + r'\s*\(.*\)\s*\{)' + ')'
            if definition == '':
                opener = re.search(fnOpener, line) if fnOpener else False
                if opener:
                    # ignore everything before the function opener
                    searchForBrackets = line[opener.start():]

            openBrackets = reduce(countBrackets, re.findall('[()]', searchForBrackets), openBrackets)

            definition += line
            if openBrackets == 0:
                break
        return definition

    def parse(self, line):
        try:
            out = self.parseFunction(line)  # (name, args, retval, options)
            if (out):
                return self.formatFunctions(*out)
            return None
        except:
            # TODO show exception if dev\debug mode
            return None

        return None

    def parseFunction(self, line):
        para = "(?P<name>[a-zA-Z_][a-zA-Z0-9_:.]*)\s*"
        arge = "\(\s*(?P<args>.*)\)"
        res = re.search(para+arge, line)
        if not res:
            return None

        #函数名
        name = res.group('name') or ''
        #参数
        args = res.group('args')
        return (name, args, None)

    def formatFunctions(self, name, args, retval):
        out = []

        #描述
        # description = ('[%s%sfuncdesc]' % (escape(name), ' ' if name else ''))
        description = "description"
        out.append("${1:%s}" % description)

        #参数
        if (args):
            # remove comments inside the argument list.
            args = re.sub(r'/\*.*?\*/', '', args)
            blocks = splitByCommas(args)
            for argName in blocks:
                format_str = "@param %s"
                argNameStr = escape(argName)
                format_str = format_str % argNameStr
                out.append(format_str)

        return out