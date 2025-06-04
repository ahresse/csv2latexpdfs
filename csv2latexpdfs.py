#!/usr/bin/env python3
import argparse
import csv
import jinja2
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional, TextIO, Union


class PDFGeneratorError(Exception):
    """Custom exception for PDF generation errors."""
    def __init__(self, message: str, filename: Optional[str] = None, line_number: Optional[int] = None):
        self.message = message
        self.filename = filename
        self.line_number = line_number
        super().__init__(self.formatted_message)

    @property
    def formatted_message(self) -> str:
        msg = self.message
        if self.filename:
            msg = f"{self.filename}: {msg}"
        if self.line_number:
            msg = f"{msg} (line {self.line_number})"
        return msg


class PDFGenerator:
    """Generates PDF files from a jinja2 template with LaTeX syntax."""
    
    LATEX_SPECIAL_CHARS = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
    }

    def __init__(self, template_path: Union[str, Path]):
        """Initialize the PDF generator with a template.
        
        Args:
            template_path: Path to the jinja2 template file.
            
        Raises:
            PDFGeneratorError: If template file is not found or has syntax errors.
        """
        self.template_path = Path(template_path).absolute()
        self.template_dir = self.template_path.parent
        self.template_name = self.template_path.name
        
        self.env = self._create_jinja2_environment()
        self.template = self._load_template()

    def _create_jinja2_environment(self) -> jinja2.Environment:
        """Create a jinja2 environment configured for LaTeX compatibility."""
        return jinja2.Environment(
            block_start_string=r'\BLOCK{',
            block_end_string=r'}',
            variable_start_string=r'\VAR{',
            variable_end_string=r'}',
            comment_start_string=r'\#{',
            comment_end_string=r'}',
            line_statement_prefix=r'%-',
            line_comment_prefix=r'%#',
            trim_blocks=True,
            autoescape=False,
            undefined=jinja2.StrictUndefined,
            loader=jinja2.FileSystemLoader(self.template_dir)
        )

    def _load_template(self) -> jinja2.Template:
        """Load and return the template file.
        
        Raises:
            PDFGeneratorError: If template loading fails.
        """
        try:
            return self.env.get_template(self.template_name)
        except jinja2.exceptions.TemplateNotFound as e:
            raise PDFGeneratorError(f"Template not found: {e.name}")
        except jinja2.exceptions.TemplateSyntaxError as e:
            raise PDFGeneratorError(f"Syntax error: {e.message}", filename=e.name, line_number=e.lineno)

    @staticmethod
    def _escape_latex(text: str) -> str:
        """Escape special LaTeX characters in a string."""
        return ''.join(PDFGenerator.LATEX_SPECIAL_CHARS.get(c, c) for c in text)

    def generate_pdf(self, substitutions: Dict[str, str], destination: Union[str, Path]) -> None:
        """Generate a PDF file from the template with given substitutions.
        
        Args:
            substitutions: Dictionary of template variables and their values.
            destination: Path for the output PDF (without .pdf extension).
            
        Raises:
            PDFGeneratorError: If PDF generation fails.
        """
        destination = Path(destination).with_suffix('.pdf')
        error_log = destination.with_suffix('.error_log')
        
        try:
            # Escape LaTeX special characters in substitutions
            escaped_subs = {k: self._escape_latex(str(v)) for k, v in substitutions.items()}
            tex_source = self.template.render(escaped_subs).encode('utf-8')
        except jinja2.UndefinedError as e:
            raise PDFGeneratorError(f"{self._template.filename}: Undefined variable in template: {e.message}")
        except UnicodeEncodeError as e:
            raise PDFGeneratorError(f"Encoding error: {e}")

        with tempfile.NamedTemporaryFile(suffix='.tex', dir=os.curdir, delete=False) as tmp_tex:
            tmp_tex.write(tex_source)
            tmp_path = Path(tmp_tex.name)

        try:
            self._run_pdflatex(tmp_path)
            self._move_output_files(tmp_path, destination, error_log)
        except subprocess.CalledProcessError as e:
            raise PDFGeneratorError(
                f"pdflatex failed with exit code {e.returncode}. See {error_log} for details."
            )
        finally:
            self._cleanup_temp_files(tmp_path)

    def _run_pdflatex(self, tex_path: Path) -> None:
        """Run pdflatex on the given .tex file."""
        with open(os.devnull, 'w') as devnull:
            subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                check=True,
                stdout=devnull,
                stderr=devnull,
                cwd=tex_path.parent
            )

    def _move_output_files(self, tex_path: Path, pdf_dest: Path, error_log: Path) -> None:
        """Move generated PDF and handle error logs."""
        temp_pdf = tex_path.with_suffix('.pdf')
        temp_log = tex_path.with_suffix('.log')
        
        if temp_pdf.exists():
            temp_pdf.replace(pdf_dest)

        else:
            if temp_log.exists():
                temp_log.replace(error_log)
            raise PDFGeneratorError("PDF generation failed. %s file not produced.", pdf_dest)

    def _cleanup_temp_files(self, tex_path: Path) -> None:
        """Clean up temporary files from pdflatex."""
        for ext in ['.aux', '.log', '.out']:
            temp_file = tex_path.with_suffix(ext)
            if temp_file.exists():
                temp_file.unlink()
        if tex_path.exists():
            tex_path.unlink()


def read_substitutions(substitutions_file: TextIO) -> Iterator[Dict[str, str]]:
    """Read substitutions from a file, automatically detecting CSV or key=value format.
    
    Args:
        substitutions_file: File object to read from.
        
    Yields:
        Dictionaries of substitutions for each PDF to generate.
    """
    filename = substitutions_file.name.lower()
    
    if filename.endswith('.csv'):
        yield from read_csv_substitutions(substitutions_file)
    else:
        yield from read_key_value_substitutions(substitutions_file)


def read_csv_substitutions(csv_file: TextIO) -> Iterator[Dict[str, str]]:
    """Read substitutions from a CSV file."""
    try:
        reader = csv.DictReader(csv_file)
        for row in reader:
            yield {k: v for k, v in row.items() if k}  # Skip empty keys
    except csv.Error as e:
        raise PDFGeneratorError(f"CSV parsing error: {e}", filename=csv_file.name)


def read_key_value_substitutions(text_file: TextIO) -> Iterator[Dict[str, str]]:
    """Read substitutions from key=value pairs."""
    pattern = re.compile(r'("[^"]+"|[^ =]+)\s*=\s*("[^"]*"|[^ ]*)')
    
    for line_number, line in enumerate(text_file, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        try:
            matches = pattern.findall(line)
            if not matches:
                raise ValueError("No valid key=value pairs found")
                
            substitutions = {
                k.strip('"'): v.strip('"') 
                for k, v in matches
                if k.strip()  # Skip empty keys
            }
            yield substitutions
            
        except ValueError as e:
            raise PDFGeneratorError(
                f"Invalid key=value format: {e}",
                filename=text_file.name,
                line_number=line_number
            )


@contextmanager
def working_directory(path: Union[str, Path]):
    """Context manager for temporarily changing the working directory."""
    original_dir = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Generate PDF files from CSV using LaTeX templates',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        'template',
        type=Path,
        help='LaTeX template file with jinja2 syntax'
    )
    parser.add_argument(
        'substitutions',
        nargs='?',
        type=argparse.FileType('r'),
        default=None,
        help='Input file with substitutions (CSV or key=value format). '
             'Use "output_file" key to specify destination for each PDF'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,
        help='Directory to output PDF'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed processing information'
    )
    
    args = parser.parse_args()

    try:
        # Initialize PDF generator
        pdf_generator = PDFGenerator(args.template)
        
        # Set output dir if specified, current program dir as default
        output_dir = args.output or Path(__file__).parent.resolve()
        
        # Create directory (with parents if needed)
        output_dir.mkdir(parents=True, exist_ok=True)
                
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as tmpdir, working_directory(tmpdir):
            if args.substitutions is sys.stdin and sys.stdin.isatty():
                print("Enter substitutions as key=value pairs (one set per line):", file=sys.stderr)
                print("  key1=value1 key2=value2 output_file=path/to/output", file=sys.stderr)
                
            # Process each set of substitutions
            success_count = 0
            for line_number, substitutions in enumerate(read_substitutions(args.substitutions), 1):
                output_path = Path(
                    str(output_dir),
                    substitutions.pop('output_file', str(args.template.stem + (f"_{line_number}")))
                ).with_suffix('')
                                
                try:
                    pdf_generator.generate_pdf(substitutions, output_path)
                    if args.verbose:
                        print(f"Generated: {output_path}.pdf")
                    success_count += 1
                except PDFGeneratorError as e:
                    print(f"Error: {e.formatted_message}", file=sys.stderr)
                    
            if args.verbose:
                print(f"\nSuccessfully generated {success_count} PDF file(s)")
                
    except PDFGeneratorError as e:
        print(f"Error: {e.formatted_message}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
