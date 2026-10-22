const fs = require('fs');
const sharp = require('sharp');
sharp(fs.readFileSync(process.argv[2]), { density: 180, limitInputPixels: 20000000 })
  .resize({width:1800, height:1800, fit:'inside'})
  .flatten({background:'#ffffff'}).png().toFile(process.argv[3])
  .catch(e => {console.error(e.message);process.exit(1)});
