# Protótipo em Godot — mesmo roteiro, tempos e medidas do protótipo QML.
# O roteiro é uma função assíncrona (await) e os efeitos são Tweens.
#
#   godot --path prototipos/godot                 # janela transparente
#   godot --path prototipos/godot -- --gravar     # com fundo, para gravar
extends Control

# --- paleta (a mesma do balão em QWidget) -------------------------------------------
const PAPEL := Color("#FBFAFF")
const TINTA := Color("#2B2D52")
const LACO := Color("#C8323C")
const BOINA := Color("#EEEDFA")
const SUSSURRO := Color("#6B6E8F")

# --- geometria (igual a bubble.py) --------------------------------------------------
const BORDA := 3.5
const RAIO := 20.0
const CAUDA_ALTURA := 30.0
const CAUDA_LARGURA := 42.0
const CAUDA_X := 220.0
const BALAO_POS := Vector2(40, 20)
const BALAO_TAM := Vector2(440, 342)
const GREMLIN_POS := Vector2(110, 332)

const PERGUNTA := "como funciona o escalonador do linux?"
const RESPOSTA := "O escalonador do Linux usa o CFS, que organiza as tarefas numa árvore rubro-negra ordenada por vruntime [1]. A tarefa com menor vruntime roda primeiro [3]."

var gravando := "--gravar" in OS.get_cmdline_user_args()
var fonte := SystemFont.new()

var sprite: Sprite2D
var folhas := {}
var quadros := {"idle": 340, "grab": 60, "emote": 54}
var anim := "idle"
var acumulado := 0.0

var balao: Balao
var campo_texto: Label
var botao_texto: Label
var status: Label
var pontos: Array[Panel] = []
var pontos_caixa: HBoxContainer
var palavras_caixa: HFlowContainer
var fontes: Label
var pensando := false
var tempo := 0.0


class Balao extends Control:
	var contorno := PackedVector2Array()

	func _ready() -> void:
		contorno = Balao.calcular(size)

	func _draw() -> void:
		draw_colored_polygon(contorno, PAPEL)
		var fechado := contorno.duplicate()
		fechado.append(contorno[0])
		draw_polyline(fechado, TINTA, BORDA, true)

	# Mesmo traçado do Canvas do QML: corpo arredondado + cauda curva.
	static func calcular(t: Vector2) -> PackedVector2Array:
		var m := BORDA / 2 + 0.5
		var base := t.y - m - CAUDA_ALTURA
		var esq := CAUDA_X - CAUDA_LARGURA / 2 - 16
		var dir := CAUDA_X + CAUDA_LARGURA / 2 - 16
		var ponta := Vector2(CAUDA_X, t.y - m)
		var meio_y := base + (ponta.y - base) * 0.6
		var p := PackedVector2Array()
		_arco(p, Vector2(t.x - m - RAIO, m + RAIO), -PI / 2, 0)        # canto sup. dir.
		_arco(p, Vector2(t.x - m - RAIO, base - RAIO), 0, PI / 2)      # canto inf. dir.
		_quad(p, Vector2(dir, base), Vector2(dir - 4, meio_y), ponta)  # lado de dentro
		_quad(p, ponta, Vector2(esq + 4, meio_y), Vector2(esq, base))  # lado de fora
		_arco(p, Vector2(m + RAIO, base - RAIO), PI / 2, PI)           # canto inf. esq.
		_arco(p, Vector2(m + RAIO, m + RAIO), PI, 3 * PI / 2)          # canto sup. esq.
		return p

	static func _arco(p: PackedVector2Array, c: Vector2, de: float, ate: float) -> void:
		for i in 13:
			var a := lerpf(de, ate, i / 12.0)
			p.append(c + Vector2(cos(a), sin(a)) * RAIO)

	static func _quad(p: PackedVector2Array, a: Vector2, c: Vector2, b: Vector2) -> void:
		for i in 17:
			var s := i / 16.0
			p.append(a.lerp(c, s).lerp(c.lerp(b, s), s))


func _ready() -> void:
	fonte.font_names = PackedStringArray(["Nunito", "Quicksand", "Noto Sans"])
	if gravando:
		_fundo()
	_montar_gremlin()
	_montar_balao()
	if not gravando:
		_clique_so_no_que_aparece()
	_roteiro()


func _unhandled_input(evento: InputEvent) -> void:
	if evento.is_action_pressed("ui_cancel"):
		get_tree().quit()


# --- montagem ---------------------------------------------------------------------------

func _fundo() -> void:
	var g := Gradient.new()
	g.set_color(0, Color("#1b1b22"))
	g.set_color(1, Color("#0d0d12"))
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill_from = Vector2(0, 0)
	tex.fill_to = Vector2(0, 1)
	var fundo := TextureRect.new()
	fundo.texture = tex
	fundo.size = size
	fundo.stretch_mode = TextureRect.STRETCH_SCALE
	add_child(fundo)


func _montar_gremlin() -> void:
	var dir := ProjectSettings.globalize_path("res://").path_join("../sprites")
	for nome in quadros:
		var img := Image.load_from_file(dir.path_join(nome + ".png"))
		folhas[nome] = ImageTexture.create_from_image(img)
	sprite = Sprite2D.new()
	sprite.centered = false
	sprite.position = GREMLIN_POS
	sprite.hframes = 10
	add_child(sprite)
	_tocar("idle")


func _tocar(nome: String) -> void:
	anim = nome
	acumulado = 0.0
	sprite.texture = folhas[nome]
	sprite.vframes = ceili(quadros[nome] / 10.0)
	sprite.frame = 0


func _rotulo(texto: String, cor: Color, tamanho: int, peso := 400) -> Label:
	var l := Label.new()
	l.text = texto
	var f := fonte
	if peso != 400:
		f = SystemFont.new()
		f.font_names = fonte.font_names
		f.font_weight = peso
	l.add_theme_font_override("font", f)
	l.add_theme_font_size_override("font_size", tamanho)
	l.add_theme_color_override("font_color", cor)
	return l


func _caixa(cor: Color, raio: int, borda := 0, cor_borda := Color.TRANSPARENT) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = cor
	s.set_corner_radius_all(raio)
	s.set_border_width_all(borda)
	s.border_color = cor_borda
	s.anti_aliasing = true
	return s


func _montar_balao() -> void:
	balao = Balao.new()
	balao.position = BALAO_POS
	balao.size = BALAO_TAM
	balao.pivot_offset = Vector2(CAUDA_X, BALAO_TAM.y)  # cresce a partir da ponta da cauda
	balao.scale = Vector2.ONE * 0.2
	balao.modulate.a = 0
	add_child(balao)

	var coluna := VBoxContainer.new()
	coluna.position = Vector2(18, 14)
	coluna.size = Vector2(BALAO_TAM.x - 32, 0)
	coluna.add_theme_constant_override("separation", 6)
	balao.add_child(coluna)

	var topo := HBoxContainer.new()
	topo.add_theme_constant_override("separation", 8)
	coluna.add_child(topo)

	var campo := Panel.new()
	campo.custom_minimum_size = Vector2(300, 34)
	campo.add_theme_stylebox_override("panel", _caixa(BOINA, 12, 2, LACO))
	topo.add_child(campo)
	campo_texto = _rotulo("Pergunte sobre o seu acervo", SUSSURRO, 13)
	campo_texto.position = Vector2(12, 7)
	campo.add_child(campo_texto)

	var botao := Panel.new()
	botao.custom_minimum_size = Vector2(86, 34)
	botao.add_theme_stylebox_override("panel", _caixa(TINTA, 12))
	topo.add_child(botao)
	botao_texto = _rotulo("Perguntar", PAPEL, 13, 600)
	botao_texto.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	botao_texto.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	botao_texto.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	botao.add_child(botao_texto)

	var fechar := _rotulo("✕", SUSSURRO, 13)
	fechar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	topo.add_child(fechar)

	status = _rotulo("", SUSSURRO, 12)
	status.custom_minimum_size.y = 18
	coluna.add_child(status)

	var area := Control.new()
	area.custom_minimum_size = Vector2(BALAO_TAM.x - 32, 150)
	coluna.add_child(area)

	pontos_caixa = HBoxContainer.new()
	pontos_caixa.position = Vector2(0, 10)
	pontos_caixa.add_theme_constant_override("separation", 7)
	pontos_caixa.modulate.a = 0
	area.add_child(pontos_caixa)
	for i in 3:
		var holder := Control.new()
		holder.custom_minimum_size = Vector2(9, 9)
		var ponto := Panel.new()
		ponto.size = Vector2(9, 9)
		ponto.add_theme_stylebox_override("panel", _caixa(TINTA, 5))
		holder.add_child(ponto)
		pontos_caixa.add_child(holder)
		pontos.append(ponto)

	palavras_caixa = HFlowContainer.new()
	palavras_caixa.size = Vector2(BALAO_TAM.x - 32, 150)
	palavras_caixa.add_theme_constant_override("h_separation", 4)
	area.add_child(palavras_caixa)

	var rodape := HBoxContainer.new()
	rodape.custom_minimum_size.y = 22
	coluna.add_child(rodape)
	fontes = _rotulo("Fontes (3) ▸", SUSSURRO, 12)
	fontes.modulate.a = 0
	rodape.add_child(fontes)
	var mola := Control.new()
	mola.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rodape.add_child(mola)
	rodape.add_child(_rotulo("☐ Incluir restritos", TINTA, 12))


func _clique_so_no_que_aparece() -> void:
	# Clique só pega no balão e no Gremlin; fora deles passa para o desktop.
	var forma := Balao.calcular(BALAO_TAM)
	for i in forma.size():
		forma[i] += BALAO_POS
	var gremlin := PackedVector2Array([GREMLIN_POS, GREMLIN_POS + Vector2(300, 0),
		GREMLIN_POS + Vector2(300, 300), GREMLIN_POS + Vector2(0, 300)])
	var unidas := Geometry2D.merge_polygons(forma, gremlin)
	DisplayServer.window_set_mouse_passthrough(unidas[0])


# --- animação contínua ------------------------------------------------------------------

func _process(delta: float) -> void:
	tempo += delta
	acumulado += delta * 25.0  # 25 fps, como o sprite-map.json
	while acumulado >= 1.0:
		acumulado -= 1.0
		sprite.frame = (sprite.frame + 1) % quadros[anim]
	if pensando or pontos_caixa.modulate.a > 0:
		for i in 3:  # mesmo ciclo de 880 ms dos pontinhos do QML
			var t := fmod(tempo - i * 0.14 + 10.0, 0.88)
			var y := 0.0
			if t < 0.22:
				y = -7.0 * ease_out_quad(t / 0.22)
			elif t < 0.48:
				y = -7.0 * (1.0 - pow((t - 0.22) / 0.26, 2))
			pontos[i].position.y = y


func ease_out_quad(x: float) -> float:
	return 1.0 - (1.0 - x) * (1.0 - x)


# --- roteiro (idêntico ao do QML; tempos em segundos) -------------------------------------

func _esperar(s: float) -> void:
	await get_tree().create_timer(s).timeout


func _roteiro() -> void:
	while true:
		campo_texto.text = "Pergunte sobre o seu acervo"
		campo_texto.add_theme_color_override("font_color", SUSSURRO)
		status.text = ""
		botao_texto.text = "Perguntar"
		fontes.modulate.a = 0
		fontes.position.x = -8
		for filho in palavras_caixa.get_children():
			filho.queue_free()
		_tocar("idle")
		await _esperar(0.8)

		# abre: mola a partir da ponta da cauda
		var abre := create_tween().set_parallel()
		abre.tween_property(balao, "scale", Vector2.ONE, 0.42).from(Vector2.ONE * 0.2) \
			.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
		abre.tween_property(balao, "modulate:a", 1.0, 0.18).from(0.0)
		await abre.finished

		# digita a pergunta (35 ms por letra)
		campo_texto.add_theme_color_override("font_color", TINTA)
		var digita := create_tween()
		digita.tween_method(func(n: int): campo_texto.text = PERGUNTA.substr(0, n),
			0, PERGUNTA.length(), PERGUNTA.length() * 0.035)
		await digita.finished
		await _esperar(0.37)

		# envia: Gremlin pensa
		botao_texto.text = "Cancelar"
		status.text = "Buscando no acervo…"
		pensando = true
		create_tween().tween_property(pontos_caixa, "modulate:a", 1.0, 0.2)
		_tocar("grab")
		await _esperar(2.3)

		# resposta chegando, palavra por palavra (90 ms)
		pensando = false
		create_tween().tween_property(pontos_caixa, "modulate:a", 0.0, 0.2)
		status.text = "Respondendo…"
		# Uma animação só para todas as palavras, como no QML: um await
		# por palavra acumularia o arredondamento de cada espera.
		var lista := RESPOSTA.split(" ")
		var chegaram := [0]
		var chega := create_tween()
		chega.tween_method(func(n: int):
			while chegaram[0] < n:
				_entrar_palavra(lista[chegaram[0]])
				chegaram[0] += 1,
			0, lista.size(), lista.size() * 0.09)
		await chega.finished
		await _esperar(0.2)

		# pronto: pulinho do balão, fontes deslizam, Gremlin comemora
		botao_texto.text = "Perguntar"
		status.text = "Pronto em 4,4 s, 11,8 tokens/s"
		_tocar("emote")
		var pulo := create_tween()
		pulo.tween_property(balao, "scale", Vector2.ONE * 1.04, 0.09) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
		pulo.tween_property(balao, "scale", Vector2.ONE, 0.32) \
			.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
		var desliza := create_tween().set_parallel()
		desliza.tween_property(fontes, "modulate:a", 1.0, 0.26)
		desliza.tween_property(fontes, "position:x", 0.0, 0.32) \
			.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		await _esperar(0.41 + 3.92)  # emote: 2 voltas de 54 quadros a 25 fps

		_tocar("idle")
		await _esperar(1.0)

		# fecha
		var fecha := create_tween().set_parallel()
		fecha.tween_property(balao, "scale", Vector2.ONE * 0.8, 0.22) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
		fecha.tween_property(balao, "modulate:a", 0.0, 0.22)
		await fecha.finished
		await _esperar(1.5)


func _entrar_palavra(palavra: String) -> void:
	var caixa := Control.new()
	# SHRINK_BEGIN: sem isso o HFlowContainer estica as palavras para
	# encher a linha (texto justificado, com buracos).
	caixa.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var rotulo := _rotulo(palavra, TINTA, 13)
	caixa.add_child(rotulo)
	caixa.custom_minimum_size = fonte.get_string_size(palavra, HORIZONTAL_ALIGNMENT_LEFT, -1, 13) + Vector2(0, 4)
	palavras_caixa.add_child(caixa)
	rotulo.modulate.a = 0
	rotulo.position.y = 6
	var t := create_tween().set_parallel()
	t.tween_property(rotulo, "modulate:a", 1.0, 0.18)
	t.tween_property(rotulo, "position:y", 0.0, 0.22).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
