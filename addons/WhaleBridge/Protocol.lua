-- Independent wire format. No network, disk IO, input simulation or secret values.
WhaleWire = {}
local W = WhaleWire
W.columns, W.rows, W.cell = 128, 16, 2
W.marker = {5, 0, 5, 2, 5, 0, 3, 6}
W.levels = {24, 93, 162, 231}
W.maxBody = 1400

local function quote(s)
    return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end

function W.json(v)
    local t = type(v)
    if t == 'string' then return quote(v) end
    if t == 'number' or t == 'boolean' then return tostring(v) end
    if t ~= 'table' then return 'null' end
    local parts = {}
    if #v > 0 then
        for i = 1, #v do parts[i] = W.json(v[i]) end
        return '[' .. table.concat(parts, ',') .. ']'
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do parts[#parts + 1] = quote(k) .. ':' .. W.json(v[k]) end
    return '{' .. table.concat(parts, ',') .. '}'
end

local function uint(n, bytes)
    local parts = {}
    for i = bytes - 1, 0, -1 do
        parts[#parts + 1] = string.char(math.floor(n / 256 ^ i) % 256)
    end
    return table.concat(parts)
end

function W.packet(state, sequence)
    local body = W.json(state)
    if #body > W.maxBody then error('WhaleBridge payload exceeds wire capacity') end
    local a, b = 1, 0
    for i = 1, #body do
        a = (a + string.byte(body, i)) % 65521
        b = (b + a) % 65521
    end
    return 'WGB1' .. uint(#body, 2) .. uint(sequence, 4) .. uint(b * 65536 + a, 4) .. body
end

-- Each texture carries 2 bits per RGB channel. Calibrate all 64 colors: macOS
-- color management mixes channels, so a grayscale-only ramp is insufficient.
function W.colors(packet)
    local colors = {}
    for _, n in ipairs(W.marker) do
        colors[#colors + 1] = {math.floor(n / 4) * 255, math.floor(n / 2) % 2 * 255, n % 2 * 255}
    end
    for value = 0, 63 do
        colors[#colors + 1] = {W.levels[math.floor(value / 16) + 1], W.levels[math.floor(value / 4) % 4 + 1], W.levels[value % 4 + 1]}
    end
    local bits, count = 0, 0
    for i = 1, #packet do
        bits, count = bits * 256 + string.byte(packet, i), count + 8
        while count >= 6 do
            count = count - 6
            local value = math.floor(bits / 2 ^ count)
            bits = bits % 2 ^ count
            colors[#colors + 1] = {W.levels[math.floor(value / 16) + 1], W.levels[math.floor(value / 4) % 4 + 1], W.levels[value % 4 + 1]}
        end
    end
    if count > 0 then
        local value = bits * 2 ^ (6 - count)
        colors[#colors + 1] = {W.levels[math.floor(value / 16) + 1], W.levels[math.floor(value / 4) % 4 + 1], W.levels[value % 4 + 1]}
    end
    return colors
end
