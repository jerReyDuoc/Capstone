"""
HU-34 criterio 4 · Plantillas del mapa de datos por rubro.

Cada plantilla trae los sistemas, bases de datos, terceros y flujos típicos de un rubro, más
una base común a toda empresa (remuneraciones, previsión, correo corporativo). Sirven para no
partir de una hoja en blanco: todo lo que se agrega desde una plantilla queda "por confirmar"
(pendiente_revision) hasta que la empresa lo revise, y nunca reemplaza lo que ya existe
(se omite lo que ya está en el mapa, por clave o por nombre).

Las categorías y los titulares usan los códigos del catálogo común (catalogo_tratamiento.py);
tests/test_hu34_mapa_datos.py verifica que todos existan y que cada flujo apunte a elementos
de la misma plantilla.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

VERSION_PLANTILLAS = "2026.11"


@dataclass(frozen=True)
class ElementoPlantilla:
    clave: str
    tipo: str
    subtipo: str
    nombre: str
    descripcion: str
    pais: str | None = "CL"
    responsable: str | None = None
    datos: tuple[str, ...] = ()
    titulares: tuple[str, ...] = ()
    rol: str | None = None
    nna: bool = False
    proveedor: str | None = None


@dataclass(frozen=True)
class FlujoPlantilla:
    origen: str
    destino: str
    finalidad: str
    datos: tuple[str, ...] = ()
    titulares: tuple[str, ...] = ()
    frecuencia: str | None = None
    medio: str | None = None
    nna: bool = False


@dataclass(frozen=True)
class Plantilla:
    codigo: str
    nombre: str
    descripcion: str
    elementos: tuple[ElementoPlantilla, ...]
    flujos: tuple[FlujoPlantilla, ...]


E, F = ElementoPlantilla, FlujoPlantilla

# ------------------------------------------------------------------ base común a toda empresa
_COMUN_E = (
    E("comun_colaboracion", "sistema", "colaboracion", "Correo y herramientas de colaboración",
      "Correo corporativo, calendario y documentos compartidos.", "US", "Jefatura de TI",
      ("identificacion", "contacto", "comunicaciones"), ("trabajadores", "clientes", "contactos_proveedores")),
    E("comun_rrhh", "sistema", "rrhh", "Sistema de remuneraciones y RR.HH.",
      "Contratos, liquidaciones de sueldo, vacaciones y licencias.", "CL", "Gerencia de Personas",
      ("identificacion", "contacto", "laborales", "financieros", "salud"),
      ("trabajadores", "ex_trabajadores", "beneficiarios")),
    E("comun_bd_personal", "base_datos", "relacional", "Base de datos del personal",
      "Fichas del personal, cargas familiares y antecedentes laborales.", "CL", "Gerencia de Personas",
      ("identificacion", "contacto", "laborales", "financieros", "salud", "afiliacion"),
      ("trabajadores", "ex_trabajadores", "postulantes", "beneficiarios")),
    E("comun_prevision", "tercero", "organismo_publico", "Instituciones de previsión y salud",
      "AFP, Fonasa o isapres y mutualidad, a las que se informan las cotizaciones.", "CL",
      datos=("identificacion", "laborales", "financieros"), titulares=("trabajadores",), rol="obligacion_legal"),
    E("comun_banco", "tercero", "pagos", "Banco para el pago de remuneraciones",
      "Banco que deposita las remuneraciones en las cuentas del personal.", "CL",
      datos=("identificacion", "financieros"), titulares=("trabajadores",), rol="encargado"),
    E("comun_respaldos", "base_datos", "respaldo", "Respaldos de información",
      "Copias de seguridad de los sistemas y bases de datos.", "CL", "Jefatura de TI",
      ("identificacion", "contacto", "laborales", "financieros"), ("trabajadores", "clientes")),
)
_COMUN_F = (
    F("comun_rrhh", "comun_bd_personal", "Gestionar la relación laboral y las remuneraciones",
      ("identificacion", "laborales", "financieros", "salud"), ("trabajadores",), "tiempo_real", "replicacion"),
    F("comun_rrhh", "comun_prevision", "Pagar e informar las cotizaciones previsionales y de salud",
      ("identificacion", "laborales", "financieros"), ("trabajadores",), "mensual", "archivo"),
    F("comun_rrhh", "comun_banco", "Pagar las remuneraciones",
      ("identificacion", "financieros"), ("trabajadores",), "mensual", "archivo"),
    F("comun_bd_personal", "comun_respaldos", "Respaldar la información del personal",
      ("identificacion", "laborales", "financieros"), ("trabajadores",), "diaria", "replicacion"),
)

# ------------------------------------------------------------------ rubros
_BANCA = Plantilla(
    "banca", "Banca y finanzas",
    "Core financiero, evaluación crediticia, banca digital, burós de información comercial y reportes al regulador.",
    _COMUN_E + (
        E("banca_core", "sistema", "aplicacion_propia", "Core financiero",
          "Cuentas, créditos, inversiones y movimientos de los clientes.", "CL", "Gerencia de Operaciones",
          ("identificacion", "contacto", "financieros", "comerciales", "solvencia"), ("clientes", "beneficiarios")),
        E("banca_digital", "sistema", "app_movil", "Banca en línea y aplicación móvil",
          "Canal digital de los clientes.", "CL", "Gerencia de Canales Digitales",
          ("identificacion", "contacto", "credenciales", "financieros", "navegacion", "geolocalizacion"),
          ("clientes", "usuarios")),
        E("banca_bd_clientes", "base_datos", "relacional", "Base de datos de clientes y productos",
          "Ficha de cliente y productos contratados.", "CL", "Gerencia de Operaciones",
          ("identificacion", "contacto", "financieros", "comerciales", "solvencia", "socioeconomicos"),
          ("clientes", "beneficiarios")),
        E("banca_scoring", "sistema", "sistema_ia", "Modelo de evaluación crediticia",
          "Calcula el riesgo de crédito y apoya la aprobación de solicitudes.", "CL", "Gerencia de Riesgo",
          ("identificacion", "solvencia", "perfilamiento", "socioeconomicos"), ("clientes", "prospectos")),
        E("banca_kyc", "tercero", "proveedor_servicios", "Proveedor de verificación de identidad",
          "Valida la identidad del cliente al abrir productos (incluye biometría facial).", "US",
          datos=("identificacion", "biometricos", "imagen_voz"), titulares=("clientes",), rol="encargado"),
        E("banca_buro", "tercero", "proveedor_servicios", "Burós de información comercial",
          "Consulta y reporte del comportamiento de pago.", "CL",
          datos=("identificacion", "solvencia"), titulares=("clientes", "prospectos"), rol="cesionario"),
        E("banca_regulador", "tercero", "organismo_publico", "Regulador financiero",
          "Reportes normativos al regulador del mercado financiero.", "CL",
          datos=("identificacion", "financieros", "solvencia"), titulares=("clientes",), rol="obligacion_legal"),
    ),
    _COMUN_F + (
        F("banca_digital", "banca_core", "Operar los productos del cliente en línea",
          ("identificacion", "credenciales", "financieros"), ("clientes",), "tiempo_real", "api"),
        F("banca_core", "banca_bd_clientes", "Registrar clientes, productos y movimientos",
          ("identificacion", "financieros", "comerciales"), ("clientes",), "tiempo_real", "replicacion"),
        F("banca_bd_clientes", "banca_scoring", "Evaluar el riesgo de crédito",
          ("identificacion", "solvencia", "socioeconomicos"), ("clientes", "prospectos"), "tiempo_real", "api"),
        F("banca_digital", "banca_kyc", "Verificar la identidad del cliente",
          ("identificacion", "biometricos", "imagen_voz"), ("clientes",), "bajo_demanda", "api"),
        F("banca_scoring", "banca_buro", "Consultar el comportamiento de pago",
          ("identificacion", "solvencia"), ("clientes", "prospectos"), "bajo_demanda", "api"),
        F("banca_bd_clientes", "banca_regulador", "Cumplir los reportes normativos",
          ("identificacion", "financieros"), ("clientes",), "mensual", "archivo"),
    ),
)

_SALUD = Plantilla(
    "salud", "Salud",
    "Ficha clínica, agenda, telemedicina, laboratorios externos y aseguradores de salud.",
    _COMUN_E + (
        E("salud_ficha", "sistema", "aplicacion_propia", "Ficha clínica electrónica",
          "Atenciones, diagnósticos, recetas y evolución de los pacientes.", "CL", "Dirección Médica",
          ("identificacion", "contacto", "salud", "perfil_biologico"), ("pacientes", "apoderados")),
        E("salud_agenda", "sistema", "saas", "Agenda y reserva de horas",
          "Reserva de horas en línea y recordatorios.", "US", "Jefatura de Admisión",
          ("identificacion", "contacto", "salud"), ("pacientes", "apoderados")),
        E("salud_bd_clinica", "base_datos", "relacional", "Base de datos clínica",
          "Historial clínico, exámenes e imágenes médicas.", "CL", "Dirección Médica",
          ("identificacion", "salud", "perfil_biologico", "imagen_voz"), ("pacientes",)),
        E("salud_telemedicina", "sistema", "saas", "Plataforma de telemedicina",
          "Consultas por videollamada y mensajería con el paciente.", "US", "Dirección Médica",
          ("identificacion", "contacto", "salud", "imagen_voz", "comunicaciones"), ("pacientes",)),
        E("salud_laboratorio", "tercero", "proveedor_servicios", "Laboratorio clínico externo",
          "Procesa exámenes y devuelve resultados.", "CL",
          datos=("identificacion", "salud", "perfil_biologico"), titulares=("pacientes",), rol="encargado"),
        E("salud_asegurador", "tercero", "pagos", "Fonasa, isapres y seguros de salud",
          "Bonos, reembolsos y programas de salud.", "CL",
          datos=("identificacion", "salud", "financieros"), titulares=("pacientes", "beneficiarios"),
          rol="obligacion_legal"),
    ),
    _COMUN_F + (
        F("salud_agenda", "salud_ficha", "Registrar la reserva y el motivo de consulta",
          ("identificacion", "contacto", "salud"), ("pacientes",), "tiempo_real", "api"),
        F("salud_ficha", "salud_bd_clinica", "Mantener la ficha clínica",
          ("identificacion", "salud"), ("pacientes",), "tiempo_real", "replicacion"),
        F("salud_telemedicina", "salud_ficha", "Registrar las atenciones a distancia",
          ("identificacion", "salud", "comunicaciones"), ("pacientes",), "tiempo_real", "api"),
        F("salud_ficha", "salud_laboratorio", "Solicitar y recibir exámenes",
          ("identificacion", "salud"), ("pacientes",), "diaria", "api"),
        F("salud_ficha", "salud_asegurador", "Emitir bonos y gestionar reembolsos",
          ("identificacion", "salud", "financieros"), ("pacientes", "beneficiarios"), "diaria", "api"),
    ),
)

_RETAIL = Plantilla(
    "retail", "Retail y e-commerce",
    "Tienda en línea, ERP, programa de fidelización, pagos, despacho y marketing digital.",
    _COMUN_E + (
        E("retail_ecommerce", "sistema", "ecommerce", "Tienda en línea",
          "Catálogo, carro de compras y cuentas de clientes.", "US", "Gerencia E-commerce",
          ("identificacion", "contacto", "credenciales", "comerciales", "navegacion"), ("clientes", "usuarios")),
        E("retail_erp", "sistema", "erp", "ERP de ventas y operaciones",
          "Pedidos, boletas, facturas, inventario y devoluciones.", "CL", "Gerencia de Operaciones",
          ("identificacion", "contacto", "comerciales", "financieros"), ("clientes", "contactos_proveedores")),
        E("retail_crm", "sistema", "crm", "CRM y programa de fidelización",
          "Puntos, segmentación de clientes y campañas.", "US", "Gerencia de Marketing",
          ("identificacion", "contacto", "comerciales", "perfilamiento"), ("clientes", "prospectos")),
        E("retail_bd_clientes", "base_datos", "relacional", "Base de datos de clientes",
          "Clientes, direcciones de despacho e historial de compras.", "CL", "Gerencia de Operaciones",
          ("identificacion", "contacto", "comerciales"), ("clientes",)),
        E("retail_pagos", "tercero", "pagos", "Pasarela de pagos",
          "Procesa los pagos con tarjeta y transferencias.", "CL",
          datos=("identificacion", "financieros"), titulares=("clientes",), rol="encargado"),
        E("retail_courier", "tercero", "logistica", "Empresa de despacho",
          "Entrega los pedidos a domicilio.", "CL",
          datos=("identificacion", "contacto", "geolocalizacion"), titulares=("clientes",), rol="encargado"),
        E("retail_marketing", "tercero", "marketing", "Plataforma de marketing y analítica web",
          "Envío de campañas, publicidad digital y medición del sitio.", "US",
          datos=("contacto", "navegacion", "perfilamiento"), titulares=("clientes", "prospectos", "usuarios"),
          rol="encargado"),
    ),
    _COMUN_F + (
        F("retail_ecommerce", "retail_erp", "Registrar pedidos y emitir documentos tributarios",
          ("identificacion", "contacto", "comerciales"), ("clientes",), "tiempo_real", "api"),
        F("retail_erp", "retail_bd_clientes", "Mantener la ficha y el historial de compras",
          ("identificacion", "contacto", "comerciales"), ("clientes",), "tiempo_real", "replicacion"),
        F("retail_ecommerce", "retail_pagos", "Cobrar las compras",
          ("identificacion", "financieros"), ("clientes",), "tiempo_real", "api"),
        F("retail_erp", "retail_courier", "Despachar los pedidos",
          ("identificacion", "contacto"), ("clientes",), "diaria", "api"),
        F("retail_bd_clientes", "retail_crm", "Segmentar clientes y gestionar el programa de puntos",
          ("identificacion", "contacto", "comerciales", "perfilamiento"), ("clientes",), "diaria", "replicacion"),
        F("retail_crm", "retail_marketing", "Enviar campañas y medir resultados",
          ("contacto", "perfilamiento", "navegacion"), ("clientes", "prospectos"), "semanal", "api"),
    ),
)

_TELECOM = Plantilla(
    "telecomunicaciones", "Telecomunicaciones",
    "Facturación de servicios, CRM, registros de tráfico, atención externalizada y reportes al regulador.",
    _COMUN_E + (
        E("tel_facturacion", "sistema", "aplicacion_propia", "Sistema de facturación y planes",
          "Contratos, planes, consumos y cobros de los abonados.", "CL", "Gerencia Comercial",
          ("identificacion", "contacto", "financieros", "comerciales"), ("clientes",)),
        E("tel_crm", "sistema", "crm", "CRM y atención de clientes",
          "Solicitudes, reclamos y portabilidad.", "CL", "Gerencia de Servicio al Cliente",
          ("identificacion", "contacto", "comerciales", "comunicaciones", "imagen_voz"), ("clientes", "prospectos")),
        E("tel_bd_abonados", "base_datos", "relacional", "Base de datos de abonados",
          "Ficha de los abonados y sus servicios.", "CL", "Gerencia de TI",
          ("identificacion", "contacto", "comerciales", "financieros"), ("clientes",)),
        E("tel_trafico", "base_datos", "analitica", "Registros de tráfico y ubicación",
          "Registros de llamadas, navegación y antenas utilizadas.", "CL", "Gerencia de Red",
          ("navegacion", "geolocalizacion", "comunicaciones"), ("clientes", "usuarios")),
        E("tel_contact", "tercero", "proveedor_servicios", "Centro de contacto externo",
          "Atiende llamadas y chats de los clientes.", "PE",
          datos=("identificacion", "contacto", "comunicaciones", "imagen_voz"), titulares=("clientes",),
          rol="encargado"),
        E("tel_regulador", "tercero", "organismo_publico", "Regulador de telecomunicaciones",
          "Reportes normativos e información requerida por la autoridad.", "CL",
          datos=("identificacion", "comerciales"), titulares=("clientes",), rol="obligacion_legal"),
    ),
    _COMUN_F + (
        F("tel_crm", "tel_facturacion", "Contratar y modificar planes",
          ("identificacion", "contacto", "comerciales"), ("clientes",), "tiempo_real", "api"),
        F("tel_facturacion", "tel_bd_abonados", "Mantener la ficha de abonados",
          ("identificacion", "contacto", "financieros"), ("clientes",), "tiempo_real", "replicacion"),
        F("tel_trafico", "tel_facturacion", "Facturar el consumo",
          ("navegacion", "comunicaciones"), ("clientes",), "diaria", "archivo"),
        F("tel_crm", "tel_contact", "Atender solicitudes y reclamos",
          ("identificacion", "contacto", "comunicaciones"), ("clientes",), "tiempo_real", "api"),
        F("tel_bd_abonados", "tel_regulador", "Cumplir los reportes al regulador",
          ("identificacion", "comerciales"), ("clientes",), "mensual", "archivo"),
    ),
)

_EDUCACION = Plantilla(
    "educacion", "Educación",
    "Gestión académica, plataforma de aprendizaje, comunicación con apoderados y reportes a la autoridad educativa.",
    _COMUN_E + (
        E("edu_academico", "sistema", "aplicacion_propia", "Sistema de gestión académica",
          "Matrícula, notas, asistencia y anotaciones.", "CL", "Dirección Académica",
          ("identificacion", "contacto", "academicos", "salud", "socioeconomicos"),
          ("estudiantes", "nna", "apoderados"), nna=True),
        E("edu_lms", "sistema", "saas", "Plataforma de aprendizaje en línea",
          "Clases, tareas y evaluaciones en línea.", "US", "Coordinación de Tecnología Educativa",
          ("identificacion", "contacto", "credenciales", "academicos", "navegacion", "comunicaciones"),
          ("estudiantes", "nna"), nna=True),
        E("edu_comunicacion", "sistema", "saas", "Plataforma de comunicación con apoderados",
          "Circulares, autorizaciones y mensajería con las familias.", "US", "Dirección Académica",
          ("identificacion", "contacto", "comunicaciones"), ("apoderados", "estudiantes", "nna"), nna=True),
        E("edu_bd_estudiantes", "base_datos", "relacional", "Base de datos de estudiantes",
          "Ficha del estudiante, su familia y su historial.", "CL", "Dirección Académica",
          ("identificacion", "contacto", "academicos", "salud", "socioeconomicos", "imagen_voz"),
          ("estudiantes", "nna", "apoderados"), nna=True),
        E("edu_autoridad", "tercero", "organismo_publico", "Autoridad educativa",
          "Reportes de matrícula, asistencia y rendimiento.", "CL",
          datos=("identificacion", "academicos"), titulares=("estudiantes", "nna"), rol="obligacion_legal", nna=True),
        E("edu_alimentacion", "tercero", "proveedor_servicios", "Programa de alimentación y beneficios",
          "Entrega de beneficios y alimentación escolar.", "CL",
          datos=("identificacion", "salud", "socioeconomicos"), titulares=("estudiantes", "nna"), rol="cesionario",
          nna=True),
    ),
    _COMUN_F + (
        F("edu_academico", "edu_bd_estudiantes", "Mantener la ficha y el historial de cada estudiante",
          ("identificacion", "academicos", "salud"), ("estudiantes", "nna"), "tiempo_real", "replicacion", True),
        F("edu_academico", "edu_lms", "Crear las cuentas y cursos en la plataforma",
          ("identificacion", "contacto", "academicos"), ("estudiantes", "nna"), "diaria", "api", True),
        F("edu_academico", "edu_comunicacion", "Informar a las familias",
          ("identificacion", "contacto", "academicos"), ("apoderados", "nna"), "diaria", "api", True),
        F("edu_bd_estudiantes", "edu_autoridad", "Reportar matrícula y asistencia",
          ("identificacion", "academicos"), ("estudiantes", "nna"), "mensual", "archivo", True),
        F("edu_bd_estudiantes", "edu_alimentacion", "Asignar beneficios y alimentación",
          ("identificacion", "socioeconomicos", "salud"), ("estudiantes", "nna"), "mensual", "archivo", True),
    ),
)

_TECNOLOGIA = Plantilla(
    "tecnologia", "Tecnología y SaaS",
    "Plataforma propia, nube, registros y monitoreo, soporte a clientes y cobros recurrentes.",
    _COMUN_E + (
        E("tec_plataforma", "sistema", "aplicacion_propia", "Plataforma SaaS de la empresa",
          "Servicio que usan los clientes y sus usuarios.", "US", "Gerencia de Producto",
          ("identificacion", "contacto", "credenciales", "navegacion", "comunicaciones"), ("usuarios", "clientes")),
        E("tec_bd_usuarios", "base_datos", "relacional", "Base de datos de usuarios y clientes",
          "Cuentas, organizaciones y configuración.", "US", "Gerencia de Ingeniería",
          ("identificacion", "contacto", "credenciales", "comerciales"), ("usuarios", "clientes")),
        E("tec_logs", "base_datos", "analitica", "Registros de uso y monitoreo",
          "Eventos de uso, errores y métricas de la plataforma.", "US", "Gerencia de Ingeniería",
          ("navegacion", "identificacion"), ("usuarios",)),
        E("tec_nube", "tercero", "proveedor_nube", "Proveedor de nube",
          "Infraestructura donde se aloja la plataforma.", "US",
          datos=("identificacion", "contacto", "credenciales", "navegacion"), titulares=("usuarios", "clientes"),
          rol="encargado"),
        E("tec_soporte", "sistema", "saas", "Mesa de ayuda y soporte",
          "Tickets y conversaciones con los clientes.", "US", "Jefatura de Soporte",
          ("identificacion", "contacto", "comunicaciones"), ("clientes", "usuarios")),
        E("tec_pagos", "tercero", "pagos", "Procesador de pagos recurrentes",
          "Cobro de suscripciones.", "US",
          datos=("identificacion", "financieros", "contacto"), titulares=("clientes",), rol="encargado"),
    ),
    _COMUN_F + (
        F("tec_plataforma", "tec_bd_usuarios", "Operar las cuentas de los usuarios",
          ("identificacion", "contacto", "credenciales"), ("usuarios", "clientes"), "tiempo_real", "api"),
        F("tec_plataforma", "tec_logs", "Monitorear el uso y la seguridad",
          ("navegacion", "identificacion"), ("usuarios",), "tiempo_real", "api"),
        F("tec_bd_usuarios", "tec_nube", "Alojar los datos de la plataforma",
          ("identificacion", "contacto", "credenciales"), ("usuarios", "clientes"), "tiempo_real", "replicacion"),
        F("tec_plataforma", "tec_soporte", "Atender solicitudes de soporte",
          ("identificacion", "contacto", "comunicaciones"), ("clientes", "usuarios"), "bajo_demanda", "api"),
        F("tec_plataforma", "tec_pagos", "Cobrar las suscripciones",
          ("identificacion", "financieros"), ("clientes",), "mensual", "api"),
    ),
)

_MANUFACTURA = Plantilla(
    "manufactura", "Manufactura e industria",
    "ERP, control de acceso y asistencia, cámaras de seguridad, salud ocupacional y distribuidores.",
    _COMUN_E + (
        E("man_erp", "sistema", "erp", "ERP de producción y ventas",
          "Órdenes de compra, producción, ventas y despachos.", "CL", "Gerencia de Operaciones",
          ("identificacion", "contacto", "comerciales", "financieros"), ("clientes", "contactos_proveedores")),
        E("man_acceso", "sistema", "aplicacion_propia", "Control de acceso y asistencia",
          "Marcaje de entrada y salida y control de acceso a la planta.", "CL", "Gerencia de Personas",
          ("identificacion", "biometricos", "laborales"), ("trabajadores", "visitantes")),
        E("man_cctv", "base_datos", "archivos", "Grabaciones de cámaras de seguridad",
          "Video de las instalaciones y accesos.", "CL", "Jefatura de Seguridad",
          ("imagen_voz",), ("trabajadores", "visitantes")),
        E("man_salud_ocupacional", "tercero", "organismo_publico", "Mutualidad y salud ocupacional",
          "Accidentes laborales, exámenes preocupacionales y enfermedades profesionales.", "CL",
          datos=("identificacion", "salud", "laborales"), titulares=("trabajadores",), rol="obligacion_legal"),
        E("man_distribuidores", "tercero", "logistica", "Distribuidores y transportistas",
          "Reciben los pedidos de despacho con los datos de contacto de los clientes.", "CL",
          datos=("identificacion", "contacto"), titulares=("clientes", "contactos_proveedores"), rol="encargado"),
    ),
    _COMUN_F + (
        F("man_acceso", "comun_rrhh", "Calcular asistencia y horas extra",
          ("identificacion", "laborales"), ("trabajadores",), "diaria", "archivo"),
        F("comun_rrhh", "man_salud_ocupacional", "Informar accidentes y exámenes ocupacionales",
          ("identificacion", "salud", "laborales"), ("trabajadores",), "bajo_demanda", "correo"),
        F("man_erp", "man_distribuidores", "Despachar los pedidos",
          ("identificacion", "contacto"), ("clientes",), "diaria", "archivo"),
    ),
)

_GENERAL = Plantilla(
    "general", "Servicios y otros rubros",
    "Sitio web y formularios, CRM, clientes, facturación electrónica y marketing por correo.",
    _COMUN_E + (
        E("gen_web", "sistema", "ecommerce", "Sitio web y formularios de contacto",
          "Formularios de contacto, cotización y suscripción.", "US", "Gerencia Comercial",
          ("identificacion", "contacto", "navegacion"), ("prospectos", "clientes", "usuarios")),
        E("gen_crm", "sistema", "crm", "CRM y gestión comercial",
          "Oportunidades, contratos y seguimiento de clientes.", "US", "Gerencia Comercial",
          ("identificacion", "contacto", "comerciales"), ("clientes", "prospectos")),
        E("gen_bd_clientes", "base_datos", "relacional", "Base de datos de clientes",
          "Ficha de clientes, contratos e historial de servicios.", "CL", "Gerencia Comercial",
          ("identificacion", "contacto", "comerciales", "financieros"), ("clientes",)),
        E("gen_facturacion", "tercero", "organismo_publico", "Servicio de Impuestos Internos",
          "Emisión e información de documentos tributarios electrónicos.", "CL",
          datos=("identificacion", "comerciales", "financieros"), titulares=("clientes",), rol="obligacion_legal"),
        E("gen_mailing", "tercero", "marketing", "Plataforma de envío de correos masivos",
          "Boletines y campañas a clientes y prospectos.", "US",
          datos=("contacto", "navegacion"), titulares=("clientes", "prospectos"), rol="encargado"),
    ),
    _COMUN_F + (
        F("gen_web", "gen_crm", "Registrar solicitudes de contacto y cotizaciones",
          ("identificacion", "contacto"), ("prospectos", "clientes"), "tiempo_real", "api"),
        F("gen_crm", "gen_bd_clientes", "Mantener la ficha de clientes",
          ("identificacion", "contacto", "comerciales"), ("clientes",), "diaria", "replicacion"),
        F("gen_bd_clientes", "gen_facturacion", "Emitir documentos tributarios",
          ("identificacion", "comerciales", "financieros"), ("clientes",), "diaria", "api"),
        F("gen_crm", "gen_mailing", "Enviar boletines y campañas",
          ("contacto",), ("clientes", "prospectos"), "semanal", "api"),
    ),
)

PLANTILLAS: dict[str, Plantilla] = {p.codigo: p for p in (
    _BANCA, _SALUD, _RETAIL, _TELECOM, _EDUCACION, _TECNOLOGIA, _MANUFACTURA, _GENERAL)}

# Palabras clave del nombre del rubro (los rubros los mantiene el equipo interno y pueden crecer)
_CLAVES_RUBRO = (
    ("banca", ("banca", "banco", "finan", "segur", "credit", "fintech")),
    ("salud", ("salud", "clinic", "hospital", "medic", "farma")),
    ("retail", ("retail", "comerc", "ecommerce", "e-commerce", "tienda")),
    ("telecomunicaciones", ("telecom", "telefon", "internet")),
    ("educacion", ("educa", "colegio", "escuela", "universi", "institut")),
    ("tecnologia", ("tecnolog", "saas", "software", "digital")),
    ("manufactura", ("manufact", "industri", "fabric", "produc", "miner", "agro")),
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.lower().strip()


def plantilla_para_rubro(rubro: str | None) -> Plantilla:
    """La plantilla recomendada para el rubro de la empresa (o la general)."""
    nombre = _normalizar(rubro or "")
    for codigo, claves in _CLAVES_RUBRO:
        if any(c in nombre for c in claves):
            return PLANTILLAS[codigo]
    return PLANTILLAS["general"]


def catalogo_plantillas(rubro: str | None) -> list[dict]:
    recomendada = plantilla_para_rubro(rubro).codigo
    salida = []
    for p in PLANTILLAS.values():
        salida.append({
            "codigo": p.codigo, "nombre": p.nombre, "descripcion": p.descripcion,
            "recomendada": p.codigo == recomendada,
            "sistemas": sum(e.tipo == "sistema" for e in p.elementos),
            "bases_datos": sum(e.tipo == "base_datos" for e in p.elementos),
            "terceros": sum(e.tipo == "tercero" for e in p.elementos),
            "flujos": len(p.flujos),
            "elementos": [{"clave": e.clave, "tipo": e.tipo, "nombre": e.nombre} for e in p.elementos],
        })
    salida.sort(key=lambda x: (not x["recomendada"], x["codigo"] == "general", x["nombre"]))
    return salida
