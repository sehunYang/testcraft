// Export the approved TestCraft concept 02 to web and Windows icon formats.
const fs=require('node:fs');
const path=require('node:path');
const sharp=require('sharp');
const root=path.resolve(__dirname,'../app/static');
const source=fs.readFileSync(path.join(root,'icons/testcraft-master.png'));
(async()=>{
 // Only normalize export padding; retain the approved drawing and its details.
 const cropped=await sharp(source).trim({threshold:20}).png().toBuffer();
 const render=size=>sharp(cropped).resize(size-Math.max(2,Math.round(size*.04))*2,size-Math.max(2,Math.round(size*.04))*2,{fit:'contain',background:'#ffffff'}).extend({top:Math.max(2,Math.round(size*.04)),bottom:Math.max(2,Math.round(size*.04)),left:Math.max(2,Math.round(size*.04)),right:Math.max(2,Math.round(size*.04)),background:'#ffffff'}).png();
 for(const size of [16,24,32,48,64,128,180,192,256,512])await render(size).toFile(path.join(root,`icons/icon-${size}.png`));
 const icon=fs.readFileSync(path.join(root,'icons/icon-512.png')).toString('base64');
 const wrapper=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><title>TestCraft</title><image width="512" height="512" href="data:image/png;base64,${icon}"/></svg>`;
 fs.writeFileSync(path.join(root,'icons/testcraft.svg'),wrapper);
 // Keep the original favicon URL working for existing bookmarks.
 fs.writeFileSync(path.join(root,'icons/studio.svg'),wrapper);
 fs.copyFileSync(path.join(root,'icons/icon-192.png'),path.join(root,'favicon-192.png'));
 // Windows ICO directory containing PNG images at every common shell size.
 const sizes=[16,24,32,48,64,128,256];
 const frames=await Promise.all(sizes.map(size=>render(size).toBuffer()));
 const directory=Buffer.alloc(6+16*frames.length);directory.writeUInt16LE(1,2);directory.writeUInt16LE(frames.length,4);
 let offset=directory.length;
 frames.forEach((frame,i)=>{const pos=6+i*16;directory[pos]=directory[pos+1]=sizes[i]===256?0:sizes[i];directory.writeUInt16LE(1,pos+4);directory.writeUInt16LE(32,pos+6);directory.writeUInt32LE(frame.length,pos+8);directory.writeUInt32LE(offset,pos+12);offset+=frame.length});
 fs.writeFileSync(path.join(root,'favicon.ico'),Buffer.concat([directory,...frames]));
 console.log('TestCraft concept 02: PNG, SVG wrapper and multi-size ICO assets ready.');
})().catch(error=>{console.error(error);process.exitCode=1});
