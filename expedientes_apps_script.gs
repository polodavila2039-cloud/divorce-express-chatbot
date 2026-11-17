// Hoja de expedientes — Divorcio Express Saltillo
// Pegar en Extensiones > Apps Script de la hoja de Google e implementar como "Aplicación web".
// Recibe del chatbot una fila por cliente y la actualiza usando el teléfono como llave.
// Además muestra un PANEL para el celular: abrir la dirección /exec?clave=TU_CLAVE

var CLAVE = "CAMBIA_ESTA_CLAVE";   // la misma que pongas en Render como EXPEDIENTES_CLAVE
var NOMBRE_HOJA = "Expedientes";

function doPost(e) {
  var candado = LockService.getScriptLock();
  candado.waitLock(20000);
  try {
    var datos = JSON.parse(e.postData.contents);
    if (CLAVE === "CAMBIA_ESTA_CLAVE" || datos.clave !== CLAVE) {
      return responder({ ok: false, error: "clave" });
    }
    var libro = SpreadsheetApp.getActiveSpreadsheet();
    var hoja = libro.getSheetByName(NOMBRE_HOJA) || libro.insertSheet(NOMBRE_HOJA);
    var fila = datos.fila;                       // [[encabezado, valor], ...]

    // Encabezados: se crean la primera vez y se agregan los que falten.
    var ancho = hoja.getLastColumn();
    var encabezados = ancho ? hoja.getRange(1, 1, 1, ancho).getValues()[0] : [];
    fila.forEach(function (par) {
      if (encabezados.indexOf(par[0]) === -1) { encabezados.push(par[0]); }
    });
    hoja.getRange(1, 1, 1, encabezados.length).setValues([encabezados]).setFontWeight("bold");
    hoja.setFrozenRows(1);

    // Buscar al cliente por teléfono.
    var colTel = encabezados.indexOf("Teléfono") + 1;
    var telefono = "";
    fila.forEach(function (par) { if (par[0] === "Teléfono") { telefono = String(par[1]); } });
    var ultima = hoja.getLastRow();
    var renglon = 0;
    if (ultima > 1 && colTel > 0) {
      var telefonos = hoja.getRange(2, colTel, ultima - 1, 1).getValues();
      for (var i = 0; i < telefonos.length; i++) {
        if (String(telefonos[i][0]) === telefono) { renglon = i + 2; break; }
      }
    }
    var esNuevo = renglon === 0;
    if (esNuevo) { renglon = ultima + 1; if (renglon < 2) { renglon = 2; } }

    var rango = hoja.getRange(renglon, 1, 1, encabezados.length);
    rango.setNumberFormat("@");                  // todo como texto: nada se interpreta como fórmula
    var valores = esNuevo ? encabezados.map(function () { return ""; }) : rango.getValues()[0];
    fila.forEach(function (par) {
      if (par[0] === "Primer contacto" && !esNuevo) { return; }
      valores[encabezados.indexOf(par[0])] = par[1];
    });
    rango.setValues([valores]);
    return responder({ ok: true, renglon: renglon });
  } catch (err) {
    return responder({ ok: false, error: String(err) });
  } finally {
    candado.releaseLock();
  }
}

function responder(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------------------
// PANEL para el celular: https://script.google.com/.../exec?clave=TU_CLAVE
// ---------------------------------------------------------------------------
function doGet(e) {
  var p = (e && e.parameter) || {};
  if (CLAVE === "CAMBIA_ESTA_CLAVE" || p.clave !== CLAVE) {
    return HtmlService.createHtmlOutput("<h3 style='font-family:sans-serif'>Acceso denegado</h3>");
  }
  var hoja = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NOMBRE_HOJA);
  var filas = hoja && hoja.getLastRow() > 1 ? hoja.getDataRange().getDisplayValues() : [[]];
  var enc = filas[0], clientes = [];
  for (var i = 1; i < filas.length; i++) {
    var c = {};
    for (var j = 0; j < enc.length; j++) {
      var v = String(filas[i][j] || "").trim();
      if (v && enc[j] !== "Todos los datos") { c[enc[j]] = v; }
    }
    if (c["Teléfono"]) { clientes.push(c); }
  }
  var datos = JSON.stringify(clientes).replace(/</g, "\\u003c");
  var html = PANEL_HTML.replace("__DATOS__", datos).replace("__AHORA__",
    Utilities.formatDate(new Date(), "America/Monterrey", "dd/MM/yyyy HH:mm"));
  return HtmlService.createHtmlOutput(html)
    .setTitle("Expedientes · Divorcio Express")
    .addMetaTag("viewport", "width=device-width, initial-scale=1, maximum-scale=1");
}

var PANEL_HTML = [
'<!DOCTYPE html><html><head><meta charset="utf-8"><style>',
'*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f3f4f6;color:#111827}',
'header{background:#0f2a4a;color:#fff;padding:16px 16px 12px}header h1{font-size:19px;margin:0}header small{opacity:.75}',
'.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px}',
'.kpi{background:#fff;border-radius:12px;padding:10px;text-align:center;box-shadow:0 1px 2px #0001}',
'.kpi b{display:block;font-size:24px}.kpi span{font-size:11px;color:#6b7280}',
'.kpi.v b{color:#15803d}.kpi.a b{color:#b45309}.kpi.g b{color:#475569}',
'.svc{display:flex;gap:6px;padding:0 12px 4px;flex-wrap:wrap;font-size:12px;color:#374151}',
'.svc span{background:#e5e7eb;border-radius:20px;padding:4px 10px}',
'.filtros{display:flex;gap:6px;overflow-x:auto;padding:8px 12px}',
'.filtros button{border:0;border-radius:20px;padding:8px 14px;background:#fff;font-size:13px;white-space:nowrap;box-shadow:0 1px 2px #0001}',
'.filtros button.on{background:#0f2a4a;color:#fff}',
'#q{margin:4px 12px 8px;width:calc(100% - 24px);padding:11px 14px;border-radius:12px;border:1px solid #d1d5db;font-size:15px}',
'.card{background:#fff;margin:0 12px 10px;border-radius:14px;padding:12px 14px;box-shadow:0 1px 3px #0002;border-left:6px solid #9ca3af}',
'.card.v{border-left-color:#16a34a}.card.a{border-left-color:#f59e0b}.card.r{border-left-color:#dc2626}.card.g{border-left-color:#9ca3af}',
'.top{display:flex;justify-content:space-between;gap:8px}.nom{font-weight:600;font-size:16px}',
'.est{font-size:11px;font-weight:700;border-radius:20px;padding:3px 9px;white-space:nowrap;height:fit-content}',
'.v .est{background:#dcfce7;color:#166534}.a .est{background:#fef3c7;color:#92400e}.r .est{background:#fee2e2;color:#991b1b}.g .est{background:#f3f4f6;color:#374151}',
'.sub{font-size:13px;color:#4b5563;margin-top:4px}.plan{font-size:13px;margin-top:6px;background:#f9fafb;border-radius:8px;padding:6px 8px}',
'.btns{display:flex;gap:8px;margin-top:10px}.btns a{flex:1;text-align:center;text-decoration:none;border-radius:10px;padding:9px;font-size:14px;font-weight:600}',
'.wa{background:#22c55e;color:#fff}.tel{background:#e0e7ff;color:#1e3a8a}.mas{background:#f3f4f6;color:#111827}',
'.det{display:none;margin-top:8px;font-size:13px;border-top:1px solid #eee;padding-top:8px}.det div{padding:3px 0}.det b{color:#6b7280;font-weight:500}',
'.vacio{text-align:center;color:#6b7280;padding:30px}',
'</style></head><body>',
'<header><h1>Expedientes · Divorcio Express</h1><small>Actualizado __AHORA__ · desliza abajo y recarga para ver nuevos</small></header>',
'<div class="kpis" id="kpis"></div><div class="svc" id="svc"></div>',
'<div class="filtros" id="filtros"></div><input id="q" placeholder="Buscar nombre o teléfono">',
'<div id="lista"></div>',
'<script>',
'var C=__DATOS__;',
'function color(e){e=(e||"").toUpperCase();if(e.indexOf("ACEPT")>-1)return"v";if(e.indexOf("URGENTE")>-1)return"r";',
' if(e.indexOf("CIERRE")>-1||e.indexOf("ASESOR")>-1)return"a";return"g";}',
'function esc(s){return String(s||"").replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c];});}',
'C.sort(function(a,b){return(b["Última actualización"]||"").localeCompare(a["Última actualización"]||"");});',
'var hoy=new Date(Date.now()-6*3600*1000).toISOString().slice(0,10);',
'function cuenta(f){return C.filter(f).length;}',
'var K=[["Total",C.length,""],["Hoy",cuenta(function(c){return(c["Primer contacto"]||"").slice(0,10)===hoy;}),""],',
' ["Aceptaron pagar",cuenta(function(c){return color(c.Estado)==="v";}),"v"],',
' ["En cierre",cuenta(function(c){return color(c.Estado)==="a";}),"a"],',
' ["Urgentes",cuenta(function(c){return color(c.Estado)==="r";}),"r"],',
' ["Solo preguntan",cuenta(function(c){return color(c.Estado)==="g";}),"g"]];',
'document.getElementById("kpis").innerHTML=K.map(function(k){return"<div class=\\"kpi "+k[2]+"\\"><b>"+k[1]+"</b><span>"+k[0]+"</span></div>";}).join("");',
'var S={};C.forEach(function(c){var s=c.Servicio||"Sin elegir";S[s]=(S[s]||0)+1;});',
'document.getElementById("svc").innerHTML=Object.keys(S).map(function(s){return"<span>"+esc(s)+": <b>"+S[s]+"</b></span>";}).join("");',
'var F=[["Todos",""],["Aceptaron","v"],["En cierre","a"],["Urgentes","r"],["Preguntan","g"]],filtro="";',
'function pintaFiltros(){document.getElementById("filtros").innerHTML=F.map(function(f){',
' return"<button class=\\""+(f[1]===filtro?"on":"")+"\\" onclick=\\"filtro=\'"+f[1]+"\';pintaFiltros();pinta()\\">"+f[0]+"</button>";}).join("");}',
'var OCULTOS=["Nombre","Teléfono","Estado","Etapa","Servicio","Plan elegido"];',
'function pinta(){var q=document.getElementById("q").value.toLowerCase();',
' var L=C.filter(function(c){return(!filtro||color(c.Estado)===filtro)&&(!q||((c.Nombre||"")+" "+c["Teléfono"]).toLowerCase().indexOf(q)>-1);});',
' document.getElementById("lista").innerHTML=L.length?L.map(function(c,i){var t=String(c["Teléfono"]).replace(/\\D/g,"");',
'  var local=t.length>10?t.slice(-10):t;',
'  var det=Object.keys(c).filter(function(k){return OCULTOS.indexOf(k)<0;}).map(function(k){return"<div><b>"+esc(k)+":</b> "+esc(c[k])+"</div>";}).join("");',
'  return"<div class=\\"card "+color(c.Estado)+"\\"><div class=\\"top\\"><div class=\\"nom\\">"+esc(c.Nombre||"Sin nombre")+"</div><span class=\\"est\\">"+esc(c.Estado)+"</span></div>"+',
'   "<div class=\\"sub\\">"+esc(c.Servicio||"Sin servicio elegido")+" · "+esc(c.Etapa)+"</div>"+',
'   (c["Plan elegido"]?"<div class=\\"plan\\">💳 "+esc(c["Forma de pago"]||"")+" — "+esc(c["Plan elegido"])+"</div>":"")+',
'   "<div class=\\"btns\\"><a class=\\"wa\\" target=\\"_blank\\" href=\\"https://wa.me/"+t+"\\">WhatsApp</a><a class=\\"tel\\" href=\\"tel:"+local+"\\">Llamar</a>"+',
'   "<a class=\\"mas\\" href=\\"#\\" onclick=\\"var d=document.getElementById(\'d"+i+"\');d.style.display=d.style.display===\'block\'?\'none\':\'block\';return false\\">Ver más</a></div>"+',
'   "<div class=\\"det\\" id=\\"d"+i+"\\">"+det+"</div></div>";}).join(""):"<div class=\\"vacio\\">Sin clientes en este filtro</div>";}',
'document.getElementById("q").oninput=pinta;pintaFiltros();pinta();',
'</script></body></html>'
].join("\n");
