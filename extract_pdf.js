const fs = require('fs');
const path = require('path');

const { PDFParse } = require(path.join('C:\\Users\\Admin\\.gemini\\antigravity-ide\\tmp_pdf\\node_modules\\pdf-parse'));

const pdfPath = 'C:\\Users\\Admin\\OneDrive\\Desktop\\MAJOR_Project\\MAJOR_Project\\PROJECT_HANDOFF_Phase3_4.pdf';

async function main() {
  const parser = new PDFParse();
  const dataBuffer = fs.readFileSync(pdfPath);
  const data = await parser.parse(dataBuffer);
  const text = data.text || (data.pages ? data.pages.map(p => p.content.map(c => c.str).join(' ')).join('\n') : JSON.stringify(data));
  fs.writeFileSync('C:\\Users\\Admin\\OneDrive\\Desktop\\MAJOR_Project\\MAJOR_Project\\pdf_extracted.txt', text, 'utf8');
  console.log('Done. Keys:', Object.keys(data));
  console.log(text.substring(0, 3000));
}

main().catch(err => {
  console.error('Error:', err.message);
  console.error(err.stack);
  process.exit(1);
});
