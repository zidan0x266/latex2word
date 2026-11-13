-- pandoc filter for the prep.py and prep_achemso.py output: front-matter styles, figures without
-- wrapper tables, bibliography numbering, page and section breaks.

local div_styles = {
  fmauthors = 'Author',
  fmaffils = 'Affiliation',
  fmcorr = 'Correspondence',
  fmkeywords = 'Keywords',
  bibentries = 'Bibliography',
  tablenotes = 'Table Note',   -- achemso: threeparttable notes
}

-- achemso reference labels: ZZBIB<form><n>L<label>ZZ, form P = (label), D = label., N = label
local LABEL_FORMS = {P = '(%s)', D = '%s.', N = '%s'}

local TAB = pandoc.RawInline('openxml', '<w:r><w:tab/></w:r>')

local PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

function Div(el)
  for cls, style in pairs(div_styles) do
    if el.classes:includes(cls) then
      el.classes = {}
      el.attributes['custom-style'] = style
      return el
    end
  end
end

local function as_paras(blocks)
  local out = pandoc.List()
  for _, b in ipairs(blocks) do
    if b.t == 'Plain' then out:insert(pandoc.Para(b.content)) else out:insert(b) end
  end
  return out
end

function Figure(fig)
  return {
    pandoc.Div(as_paras(fig.content), {['custom-style'] = 'Captioned Figure'}),
    pandoc.Div(as_paras(fig.caption.long), {['custom-style'] = 'Image Caption'}),
  }
end

function Para(el)
  local c = el.content
  if #c == 1 and c[1].t == 'Str' then
    if c[1].text == 'ZZSECTIONBREAK' then return {} end  -- \linenumbers: not reproduced in Word
    if c[1].text == 'ZZPAGEBREAK' then return pandoc.RawBlock('openxml', PAGE_BREAK) end
  end
  local n = c[1] and c[1].t == 'Str' and c[1].text:match('^ZZBIB(%d+)ZZ$')
  local label = n and ('[' .. n .. ']')
  if c[1] and c[1].t == 'Str' and not n then
    local form, num, lab = c[1].text:match('^ZZBIB([PDN])(%d+)L(%w*)ZZ$')
    if form then n, label = num, string.format(LABEL_FORMS[form], lab) end
  end
  if n then
    local inl = pandoc.List({pandoc.Span({pandoc.Str(label)}, {id = 'bib' .. n}), TAB})
    local start = (c[2] and (c[2].t == 'Space' or c[2].t == 'SoftBreak')) and 3 or 2
    for i = start, #c do inl:insert(c[i]) end
    el.content = inl
    return el
  end
end
