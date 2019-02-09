#!/usr/bin/env python3
from typing import List
from dataclasses import dataclass, field
import distutils
from pathlib import Path
import os, shutil

import regex

from format_lean.line_reader import FileReader, LineReader, dismiss_line
from format_lean.renderer import Renderer


############
#  Objects #
############
@dataclass
class Paragraph:
    name: str = 'paragraph'
    content: str = ''

    def append(self, line):
        self.content = self.content + line


@dataclass
class Text:
    name: str = 'text'
    paragraphs: List[Paragraph] = field(default_factory=list)


@dataclass
class Section:
    name: str = 'section'
    title: str = ''

    def title_append(self, line):
        self.title = self.title + line

@dataclass
class SubSection(Section):
    name: str = 'subsection'
    title: str = ''

    def title_append(self, line):
        self.title = self.title + line
    
@dataclass
class Bilingual:
    """
    Base class for objects that contains both text and Lean code.
    """
    text: str = ''
    lean: str = ''

    def text_append(self, line):
        self.text = self.text + line

    def lean_append(self, line):
        self.lean = self.lean + line


@dataclass
class Definition(Bilingual):
    name: str = 'definition'


@dataclass
class ProofLine:
    name: str = 'proof-line'
    lean: str = ''
    tactic_state_left: str = ''
    tactic_state_right: str = ''


@dataclass
class ProofItem:
    name: str = 'proof-item'
    text: str = ''
    lines: List[ProofLine] = field(default_factory=list)

    def text_append(self, line):
        self.text = self.text + line

@dataclass
class Proof:
    name: str = 'proof'
    items: List[ProofItem] = field(default_factory=list)


@dataclass
class Lemma(Bilingual):
    name: str = 'lemma'
    proof: Proof = field(default_factory=Proof)

    def proof_append(self, item):
        self.proof.items.append(item)


#################
#  Line readers #
#################

class HeaderBegin(LineReader):
    regex = regex.compile(r'-- begin header\s*')

    def run(self, m, file_reader):
        file_reader.status = 'header'
        file_reader.normal_line_handler = dismiss_line
        return True


class HeaderEnd(LineReader):
    regex = regex.compile(r'-- end header\s*')

    def run(self, m, file_reader):
        file_reader.status = ''
        return True


class TextBegin(LineReader):
    regex = regex.compile(r'\s*/-\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'text'
        text = Text()
        text.paragraphs = [Paragraph()]
        file_reader.output.append(text)
        def normal_line(file_reader, line):
            text.paragraphs[-1].append(line)
        file_reader.normal_line_handler = normal_line
        def blank_line(file_reader, line):
            text.paragraphs.append(Paragraph())
        file_reader.blank_line_handler = blank_line
        return True


class TextEnd(LineReader):
    regex = regex.compile(r'-/')

    def run(self, m, file_reader):
        if file_reader.status is not 'text':
            return False
        file_reader.reset()
        return True


class SectionBegin(LineReader):
    regex = regex.compile(r'\s*/-\s*Section\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'section'
        sec = Section()
        file_reader.output.append(sec)
        def normal_line(file_reader, line):
            sec.title_append(line)
        file_reader.normal_line_handler = normal_line
        return True


class SectionEnd(LineReader):
    regex = regex.compile(r'-/')

    def run(self, m, file_reader):
        if file_reader.status is not 'section':
            return False
        file_reader.reset()
        return True


class SubSectionBegin(LineReader):
    regex = regex.compile(r'\s*/-\s*Sub-section\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'subsection'
        sec = SubSection()
        file_reader.output.append(sec)
        def normal_line(file_reader, line):
            sec.title_append(line)
        file_reader.normal_line_handler = normal_line
        return True


class SubSectionEnd(LineReader):
    regex = regex.compile(r'-/')

    def run(self, m, file_reader):
        if file_reader.status is not 'subsection':
            return False
        file_reader.reset()
        return True


class DefinitionBegin(LineReader):
    regex = regex.compile(r'\s*/-\s*Definition\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'definition_text'
        defi = Definition()
        file_reader.output.append(defi)
        def normal_line(file_reader, line):
            defi.text_append(line)
        file_reader.normal_line_handler = normal_line
        return True


class DefinitionEnd(LineReader):
    regex = regex.compile(r'-/')

    def run(self, m, file_reader):
        if file_reader.status is not 'definition_text':
            return False
        file_reader.status = 'definition_lean'
        defi = file_reader.output[-1]
        def normal_line(file_reader, line):
            defi.lean_append(line)
        file_reader.normal_line_handler = normal_line
        def blank_line(file_reader, line):
            file_reader.reset()
        file_reader.blank_line_handler = blank_line
        return True


class LemmaBegin(LineReader):
    regex = regex.compile(r'\s*/-\s*Lemma\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'lemma_text'
        lemma = Lemma()
        file_reader.output.append(lemma)
        def normal_line(file_reader, line):
            lemma.text_append(line)
        file_reader.normal_line_handler = normal_line
        return True


class LemmaEnd(LineReader):
    regex = regex.compile(r'-/')

    def run(self, m, file_reader):
        if file_reader.status is not 'lemma_text':
            return False
        file_reader.status = 'lemma_lean'
        lemma = file_reader.output[-1]
        def normal_line(file_reader, line):
            lemma.lean_append(line)
        file_reader.normal_line_handler = normal_line
        return True


class ProofBegin(LineReader):
    regex = regex.compile(r'^begin\s*$')

    def run(self, m, file_reader):
        file_reader.status = 'proof'
        file_reader.normal_line_handler = dismiss_line # Proofs shouldn't start with normal line
        return True


class ProofEnd(LineReader):
    regex = regex.compile(r'^end\s*$')  # Beware of match end

    def run(self, m, file_reader):
        if file_reader.status is not 'proof':
            return False
        file_reader.reset()
        return True


class ProofComment(LineReader):
    regex = regex.compile(r'^[\s{]*-- (.*)$')

    def run(self, m, file_reader):
        if file_reader.status == 'proof':
            item = ProofItem()
            file_reader.output[-1].proof_append(item)
            file_reader.status = 'proof_comment'
        elif file_reader.status == 'proof_comment':
            item = file_reader.output[-1].proof.items[-1]
        else:
            return False
        item.text_append(m.group(1))
        def normal_line(file_reader, line):
            file_reader.status = 'proof'
            tsl = file_reader.server.info(file_reader.filename,
                    file_reader.cur_line_nb, 1)
            tsr = file_reader.server.info(file_reader.filename,
                    file_reader.cur_line_nb, len(line))
            item.lines.append(
                    ProofLine(lean=line, 
                        tactic_state_left=tsl, tactic_state_right=tsr))
        file_reader.normal_line_handler = normal_line
        return True


def render_lean_file(inpath, outpath=None, outdir=None,
        toolchain=None, lib_path=None, templates=None):
    if toolchain:
        lean_exec_path = Path.home() / '.elan/toolchains' / toolchain / 'bin/lean'
    else:
        lean_exec_path = Path(distutils.spawn.find_executable('lean'))
    core_path = lean_exec_path.parent / '../lib/lean/library'
    lean_path = f'{core_path}:{lib_path}' if lib_path else core_path
    templates = templates or str(Path(__file__).parent / '../../templates/')

    outpath = outpath or inpath.replace('.lean', '.html')

    if outdir:
        if not Path(outdir).is_dir():
            os.makedirs(outdir)
        outpath = str(Path(outdir) / outpath)
        for path in (Path(__file__).parent / '../../').glob('*.css'):
            shutil.copy(path, outdir)
        for path in (Path(__file__).parent / '../../').glob('*.js'):
            shutil.copy(path, outdir)

    lecture_reader = FileReader(lean_exec_path, lean_path, 
            [HeaderBegin, HeaderEnd, SectionBegin, SectionEnd, SubSectionBegin,
             SubSectionEnd, TextBegin, TextEnd, DefinitionBegin,
             DefinitionEnd, LemmaBegin, LemmaEnd, ProofBegin, ProofEnd,
             ProofComment])
    lecture_reader.read_file(inpath)
    renderer = Renderer.from_file(templates)
    renderer.render(lecture_reader.output, outpath)
