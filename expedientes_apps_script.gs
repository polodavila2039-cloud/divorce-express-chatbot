// Hoja de expedientes — Divorcio Express Saltillo
// Pegar en Extensiones > Apps Script de la hoja de Google e implementar como "Aplicación web".
// Recibe del chatbot una fila por cliente y la actualiza usando el teléfono como llave.

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
