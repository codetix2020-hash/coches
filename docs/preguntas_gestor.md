# Preguntas para el gestor / asesor fiscal

Lleva estas preguntas a tu gestor antes de empezar a comprar y vender coches de forma regular.

## ITP (Impuesto de Transmisiones Patrimoniales)

1. **¿Qué tipo de ITP me aplica?** (varía por comunidad autónoma: 4%–8%)
2. **¿Hay cuotas fijas para coches viejos?** Algunas comunidades tienen cuotas mínimas.
3. **Si compro para revender como particular, ¿tengo que pagar ITP cada vez que compro?**
4. **¿Cuándo hay exención de ITP?** (en compraventa profesional para reventa, posiblemente exento)
5. **La base imponible: ¿es el precio de compra o el valor de las tablas de Hacienda si es mayor?**

## REBU (Régimen Especial de Bienes Usados)

6. **¿Me conviene darme de alta en el REBU?** Solo aplica si soy autónomo o empresa.
7. **En REBU, ¿solo pago IVA sobre el margen?** ¿Cómo lo declaro?
8. **¿Cuántos coches puedo vender al año como particular sin ser considerado empresario?**

## IRPF y declaración

9. **Si vendo 5-10 coches al año como particular, ¿tengo que declararlo?**
10. **¿Cómo tributan las ganancias en IRPF si soy particular? ¿Y si soy autónomo?**
11. **¿Necesito factura de compra para justificar el coste de adquisición?**

## Alta como autónomo / compraventa profesional

12. **¿Qué CNAE o epígrafe del IAE corresponde a la compraventa de coches?** (45.1)
13. **¿Compensa abrir una SL para esta actividad?**
14. **¿Qué documentación debo conservar de cada operación?**

## Garantías

15. **Si vendo como particular, ¿estoy obligado a dar garantía?**
16. **Si vendo como profesional (compraventa), ¿cuánto dura la garantía mínima legal?** (1 año)
17. **¿Puedo excluir la garantía en la venta?** (solo si el comprador es consciente del estado)

## Notas para Cazachollos

- Actualizar `config.yaml → itp.tipo_por_defecto` con el tipo real confirmado.
- Actualizar `config.yaml → itp.tipos_ccaa` si operas en varias comunidades.
- Si eres REBU: cambiar `yo.regimen = "rebu"` y `itp.exento_si_profesional = true`.
