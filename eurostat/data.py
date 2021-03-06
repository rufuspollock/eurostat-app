'''Code for obtaining and cleaning data from Eurostat.
'''
import os
import re
import gzip
import json

from datautil import cache, tabular
from datautil.misc import floatify
base = 'http://epp.eurostat.ec.europa.eu/NavTree_prod/everybody/BulkDownloadListing?file=data/'

cachepath = os.path.join(os.path.dirname(__file__), 'static', 'cache')
ourcache = cache.Cache(cachepath)

class Data(object):
    def download(self, dataset_id):
        '''Download a eurostat dataset based on its `dataset_id`
        '''
        fn = dataset_id + '.tsv.gz'
        url = base + fn
        # do not use retrieve as we get random ugly name
        fp = ourcache.cache_path(fn)
        if not os.path.exists(fp):
            ourcache.download(url, fp)
        newfp = fp[:-3]
        contents = gzip.GzipFile(fp).read()
        open(newfp, 'w').write(contents)
        return newfp

    def _iso3166(self):
        # ckan.net/package/iso-3166-2-digit-country-codes
        url = 'http://api.scraperwiki.com/api/1.0/datastore/getdata?&name=iso-3166-2-letter-country-codes&limit=300'
        fp = ourcache.retrieve(url)
        codes = json.load(open(fp))
        return dict([ [x['code'], x['name']] for x in codes ])

    def extract(self, newfp):
        '''Extract data from tsv file at `filepath`, clean it and save it as json
        to file with same basename and extension json

        :return: extracted data as `Tabular`.
        '''
        reader = tabular.CsvReader()
        tab = reader.read(open(newfp), dialect='excel-tab')
        # some data has blank top row!
        if not tab.header:
            tab.header = tab.data[0]
            del tab.data[0]
        alldata = [tab.header] + tab.data
        transposed = zip(*alldata)
        tab.header = transposed[0]
        # clean header coders (mainly for countries)
        isocodes = self._iso3166()
        # of form PCH_Q1_SA,BE
        def clean_code(code):
            parts = code.split(',')
            isocode = parts[1] if len(parts) > 1 else parts[0]
            return isocodes.get(isocode, isocode)
        tab.header = map(clean_code, tab.header)
        def parsedate(cell):
            if 'Q' in cell:
                items = cell.split('Q')
                return float(items[0]) + 0.25 * (int(items[1]) - 1)
            elif 'M' in cell:
                items = cell.split('M')
                return float(items[0]) + 1/12.0 * (int(items[1]) - 1)
        def cleanrow(row):
            newrow = [ x.strip() for x in row ]
            newrow = [parsedate(newrow[0])] + [ floatify(x) for x in newrow[1:] ]
            return newrow
        tab.data = map(cleanrow, transposed[1:])
        writer = tabular.JsonWriter()
        jsonfp = newfp.split('.')[0] + '.json'
        writer.write(tab, open(jsonfp, 'w'))
        return tab

    PEEI_LIST = 'peeis.json'
    def peeis(self):
        '''Scrape the Eurostat Prinicipal Economic Indicators (PEEI) list'''
        # turns out they iframe the data!
        # url = 'http://epp.eurostat.ec.europa.eu/portal/page/portal/euroindicators/peeis/'
        url = 'http://epp.eurostat.ec.europa.eu/cache/PEEIs/PEEIs_EN.html'
        fp = ourcache.retrieve(url)
        html = open(fp).read()
        tdataset_ids = re.findall(r'goToTGM.*pcode=([^&]+)&', html)
        # de-dup
        dataset_ids = []
        for _id in tdataset_ids:
            if _id not in dataset_ids:
                dataset_ids.append(_id)
        reader = tabular.HtmlReader()
        tab = reader.read(fp, 1)
        peei_titles = []
        for row in tab.data[3:]:
            series_name = row[1].strip()
            if series_name.startswith('3 month') or series_name[0] not in '%0123456789':
                peei_titles.append(series_name)
            if series_name == 'Euro-dollar exchange rate':
                break
        peeis = {}
        for count, (_id, title) in enumerate(zip(dataset_ids, peei_titles)):
            peeis[_id] = {
                'title': title,
                'order': count
                }
        dumppath = ourcache.cache_path(self.PEEI_LIST)
        json.dump(peeis, open(dumppath, 'w'), indent=2)
        print 'PEEIs extracted to %s' % dumppath
        return peeis

    def peeis_download(self):
        '''Download (and extract to json) all PEEI datasets.'''
        peei_list_fp = ourcache.cache_path(self.PEEI_LIST)
        peeis = json.load(open(peei_list_fp))
        for eurostatid in sorted(peeis.keys()):
            print 'Processing: %s' % eurostatid
            fp = self.download(eurostatid)
            self.extract(fp)
    
from datautil.clitools import _main
if __name__ == '__main__':
    _main(Data)

