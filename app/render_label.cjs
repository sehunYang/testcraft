const fs=require('fs'),sharp=require('sharp');
sharp(fs.readFileSync(process.argv[2]),{density:216,limitInputPixels:20000000}).png().toFile(process.argv[3]).catch(e=>{console.error(e.message);process.exit(1)});
